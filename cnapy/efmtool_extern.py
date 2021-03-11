import tempfile
import glob
import os
import subprocess
import numpy
import scipy

# import efmtool_link
# _java_executable = os.path.join(str(jSystem.getProperty("java.home")), "bin", "java")
_java_executable = r'E:\mpi\Anaconda3\envs\cnapy\Library\jre\bin\java'

efmtool_jar = r'E:\gwdg_owncloud\CNAgit\CellNetAnalyzer\code\ext\efmtool\lib\metabolic-efm-all.jar'

def calculate_flux_modes(st : numpy.array, reversible, reaction_names=None, metabolite_names=None, java_executable=None):
    if java_executable is None:
        java_executable = _java_executable
    if reaction_names is None:
        reaction_names = ['R'+str(i) for i in range(st.shape[1])]
    if metabolite_names is None:
        metabolite_names = ['M'+str(i) for i in range(st.shape[0])]
    
    curr_dir = os.getcwd()
    with tempfile.TemporaryDirectory() as work_dir:
        print(work_dir)
        os.chdir(work_dir)
        write_efmtool_input(st, reversible, reaction_names, metabolite_names)

        cp = subprocess.Popen([java_executable,
        "-cp", efmtool_jar, "ch.javasoft.metabolic.efm.main.CalculateFluxModes",
        '-kind', 'stoichiometry', '-arithmetic', 'double', '-zero', '1e-10',
        '-compression', 'default', '-log', 'console', '-level', 'INFO',
        '-maxthreads', '-1', '-normalize', 'min', '-adjacency-method', 'pattern-tree-minzero', 
        '-rowordering', 'MostZerosOrAbsLexMin', '-tmpdir', '.', '-stoich', 'stoich.txt', '-rev', 
        'revs.txt', '-meta', 'mnames.txt', '-reac', 'rnames.txt', '-out', 'matlab', 'efms.mat'],
        stdout = subprocess.PIPE, stderr = subprocess.PIPE, universal_newlines=True)
        # might there be a danger of deadlock in case an error produces a large text output that blocks the pipe?
        while cp.poll() is None:
            ln = cp.stdout.readlines(1) # blocks until one line has been read
            if len(ln) > 0: # suppress empty lines that can occur in case of external termination
                print(ln[0], end='')
        print(cp.stderr.readlines())
        os.chdir(curr_dir)
        if cp.poll() is 0:
            efms = read_efms_from_mat(work_dir)
        else:
            print("Emftool failure")
            efms = None

    return efms

def write_efmtool_input(st, reversible, reaction_names, metabolite_names):
    numpy.savetxt(r"stoich.txt", st)
    with open('revs.txt', 'w') as file:
        file.write(' '.join(str(x) for x in reversible))
    with open('mnames.txt', 'w') as file:
        file.write(' '.join('"' + x + '"' for x in metabolite_names))
    with open('rnames.txt', 'w') as file:
        file.write(' '.join('"' + x + '"' for x in reaction_names))

def read_efms_from_mat(folder : str) -> numpy.array:
    # taken from https://gitlab.com/csb.ethz/efmtool/
    # efmtool stores the computed EFMs in one or more .mat files. This function
    # finds them and loads them into a single numpy array.
    efm_parts : List[np.array] = []
    files_list = sorted(glob.glob(os.path.join(folder, 'efms_*.mat')))
    for f in files_list:
        mat = scipy.io.loadmat(f, verify_compressed_data_integrity=False)
        efm_parts.append(mat['mnet']['efms'][0, 0])

    return numpy.concatenate(efm_parts, axis=1)

