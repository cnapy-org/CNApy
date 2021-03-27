#%%
import os
import numpy
import tempfile

class FluxVectorContainer:
    def __init__(self, matORfname, reac_id=None):
        if type(matORfname) is str:
            l = numpy.load(matORfname) # actually has got a memmap option
            self.fv_mat = l['fv_mat']
            self.reac_id = l['reac_id']
        else:
            self.fv_mat = matORfname # each flux vector is a column in fv_mat
            self.reac_id = reac_id # corresponds to the rows of fv_mat

    def __len__(self):
        return self.fv_mat.shape[0]

    def __getitem__(self, idx):
        return{self.reac_id[i]: float(self.fv_mat[idx, i]) for i in range(len(self.reac_id)) if self.fv_mat[idx, i] != 0}

    def save(self, fname):
        numpy.savez_compressed(fname, fv_mat=self.fv_mat, reac_id=self.reac_id)

    def clear(self):
        self.fv_mat = numpy.zeros((0, 0))
        self.reac_id.clear() 

# the class below can be used to open an efmtool binary-doubles file directly as a memory map
class FluxVectorMemmap(FluxVectorContainer):
    def __init__(self, fname, reac_id, containing_temp_dir=None):
        if containing_temp_dir is not None:
            self._containing_temp_dir = containing_temp_dir # keep the temporary directory alive
            self._memmap_fname = os.path.join(containing_temp_dir.name, fname)
        else:
            self._memmap_fname = fname
            self._containing_temp_dir = None
        with open(self._memmap_fname, 'rb') as fh:
            num_efm = numpy.fromfile(fh, dtype='>i8', count=1)[0]
            num_reac = numpy.fromfile(fh, dtype='>i4', count=1)[0]
        super().__init__(numpy.memmap(self._memmap_fname, mode='r+', dtype='>d', offset=13, shape=(num_efm, num_reac), order='C'), reac_id)

    def clear(self):
        del self.fv_mat # lose the reference to the memmap (does not have a close() method)
        self.fv_mat = None 
        self._containing_temp_dir = None # if this was the last reference to the temporary directory it is now deleted
        super().clear()

    def __del__(self):
        del self.fv_mat # lose the reference to the memmap so that the later implicit deletion of the temporary directory can proceed without problems
