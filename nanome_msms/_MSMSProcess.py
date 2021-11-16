import nanome
from nanome.util import Logs
import tempfile, sys, subprocess, os

class MSMSProcess():
    def __init__(self, plugin):
        self.__plugin = plugin
        self.__process_running = False
        self._selected_only = True
        self._cut_per_chain = True

    def start_process(self, cur_complex, probe_radius = 1.4, density = 10.0, hdensity = 3.0, do_ao = True):
        positions = []
        radii = []
        molecule = cur_complex._molecules[cur_complex.current_frame]

        verts = []
        tri = []
        norms = []
        cols = []

        if self._cut_per_chain:

            count_atoms = 0
            for chain in molecule.chains:
                positions = []
                radii = []
                for atom in chain.atoms:
                    if not self._selected_only or atom.selected:
                        positions.append(atom.position)
                        radii.append(atom.vdw_radius)
                        count_atoms+=1
                if len(positions) != 0:
                    v, n, t = self.compute_MSMS(positions, radii, probe_radius, density, hdensity)
                    self.add_to_mesh(v, n, t, verts, norms, tri)
            if count_atoms == 0 and self._selected_only:
                self.__plugin.send_notification(nanome.util.enums.NotificationTypes.message, "Nothing is selected")
                self.stop_process()
                return
            if do_ao:
                aoExePath = getAOEmbreeExecutable()
                if aoExePath != "":
                    cols = runAOEmbree(aoExePath, verts, norms, tri)
        else:
            for atom in molecule.atoms:
                if not self._selected_only or atom.selected:
                    positions.append(atom.position)
                    radii.append(atom.vdw_radius)

            if len(positions) == 0 and self._selected_only:
                self.__plugin.send_notification(nanome.util.enums.NotificationTypes.message, "Nothing is selected")
                self.stop_process()
                return
            verts, norms, tri = self.compute_MSMS(positions, radii, probe_radius, density, hdensity)

            if do_ao:
                aoExePath = getAOEmbreeExecutable()
                if aoExePath != "":
                    cols = runAOEmbree(aoExePath, verts, norms, tri)

        self.__plugin.make_mesh(verts, norms, tri, cur_complex.index, cols)
    
    def compute_MSMS(self, positions, radii, probe_radius, density, hdensity):
        verts = []
        norms = []
        faces = []

        msms_input = tempfile.NamedTemporaryFile(delete=False, suffix='.xyzr')
        msms_output = tempfile.NamedTemporaryFile(delete=False, suffix='.out')
        with open(msms_input.name, 'w') as msms_file:
            for i in range(len(positions)):
                msms_file.write("{0:.5f} {1:.5f} {2:.5f} {3:.5f}\n".format(positions[i].x, positions[i].y, positions[i].z, radii[i]))
        exePath = getMSMSExecutable()

        subprocess.run(args=[exePath, "-if ", msms_input.name, "-of ", msms_output.name, "-probe_radius", str(probe_radius), "-density", str(density), "-hdensity", str(hdensity), "-no_area", "-no_rest", "-no_header"])
        if os.path.isfile(msms_output.name + ".vert") and os.path.isfile(msms_output.name + ".face"):
            verts, norms, indices = parseVerticesNormals(msms_output.name + ".vert")
            faces = parseFaces(msms_output.name + ".face")

        else:
            Logs.error("Failed to run MSMS")
        return (verts, norms, faces)

    def add_to_mesh(self, v, n, t, verts, norms, tris):
        id_v = int(len(verts) / 3)
        verts += v
        norms += n

        for i in t:
            tris.append(i + id_v)

    def stop_process(self):
        if self.__process_running:
            self.__process.stop()
        self.__process_running = False

    def __on_process_error(self, error):
        Logs.warning('Error during MSMS:')
        Logs.warning(error)

def getMSMSExecutable():
    if sys.platform == "linux" or sys.platform == "linux2":
        return "nanome_msms/MSMS_binaries/Linux/msms"
    elif sys.platform == "darwin":
        return "nanome_msms/MSMS_binaries/OSX/msms"
    elif sys.platform == "win32":
        return "nanome_msms/MSMS_binaries/Windows/msms.exe"

def getAOEmbreeExecutable():
    if sys.platform == "win32":
        return "nanome_msms/AO_binaries/Windows/AOEmbree.exe"
    elif sys.platform == "linux" or sys.platform == "linux2":
        return "nanome_msms/AO_binaries/Linux64/AOEmbree"
    return ""

def parseVerticesNormals(path):
    verts = []
    norms = []
    indices = []
    with open(path) as f:
        lines = f.readlines()
        for l in lines:
            if l.startswith("#"):
                continue
            s = l.split()
            v = [float(s[0]), float(s[1]), float(s[2])]
            n = [float(s[3]), float(s[4]), float(s[5])]
            idx = int(s[7]) - 1
            verts += v
            norms += n
            indices.append(idx)
    return (verts, norms, indices)

def parseFaces(path):
    tris = []
    with open(path) as f:
        lines = f.readlines()
        for l in lines:
            if l.startswith("#"):
                continue
            s = l.split()
            # 0 base index instead of 1 based
            t = [int(s[0]) - 1, int(s[1]) - 1, int(s[2]) - 1]
            tris += t
    return tris


def runAOEmbree(exePath, verts, norms, faces, AO_steps = 512, AO_max_dist = 50.0):
    Logs.debug("Run AOEmbree on ", len(verts)/3," vertices")
    #Write mesh to OBJ file
    ao_input = tempfile.NamedTemporaryFile(delete=False, suffix='.obj')
    with open(ao_input.name, "w") as f:
        for v in range(int(len(verts) / 3)):
            f.write("v {0:.6f} {1:.6f} {2:.6f}\n".format(verts[v * 3], verts[v * 3 + 1], verts[v * 3 + 2]))
            f.write("vn {0:.6f} {1:.6f} {2:.6f}\n".format(norms[v * 3], norms[v * 3 + 1], norms[v * 3 + 2]))
        for t in range(int(len(faces) / 3)):
            f.write("f {} {} {}\n".format(faces[t * 3] + 1, faces[t * 3 + 1] + 1, faces[t * 3 + 2] + 1))

    envi = dict(os.environ)
    if sys.platform == "linux" or sys.platform == "linux2":
        envi['LD_LIBRARY_PATH'] = os.path.dirname(os.path.abspath(exePath))

    #Run AOEmbree
    AOvalues = subprocess.run(env=envi, args=[os.path.abspath(exePath), "-n", "-i", ao_input.name, "-a", "-s", str(AO_steps), "-d", str(AO_max_dist)], capture_output=True, text=True)
    vertCol = []
    sAOValues = AOvalues.stdout.split()
    try:
        for i in range(int(len(verts) / 3)):
            ao = float(sAOValues[i])
            vertCol += [ao, ao, ao, 1.0]
    except Exception as e:
        Logs.warning("AO computation failed")
        return []

    return vertCol
