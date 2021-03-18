# %%
import os
import numpy
import zipfile
import pickle
# import sys
import tempfile

class FluxVectorContainer:
    def __init__(self, matORfname, reac_id=None):
        if type(matORfname) is str:
            l = numpy.load(matORfname)
            self.fv_mat = l['fv_mat']
            self.reac_id = l['reac_id']
        else:
            self.fv_mat = matORfname # each flux vector is a column in fv_mat
            self.reac_id = reac_id # corresponds to the rows of fv_mat
        # self.byte_order = sys.byteorder

    def __len__(self):
        return self.fv_mat.shape[1]

    def __getitem__(self, idx):
        return{self.reac_id[i]: float(self.fv_mat[i, idx]) for i in range(len(self.reac_id)) if self.fv_mat[i, idx] != 0}

    def save(self, fname):
        numpy.savez_compressed(fname, fv_mat=self.fv_mat, reac_id=self.reac_id)

    def write_efm_info(self, zf, offset):
        zf.writestr('efm_info', pickle.dumps({'num_reac': self.fv_mat.shape[0], 'num_efm': self.fv_mat.shape[1],
                    'reac_id': self.reac_id, 'offset': offset, 'dtype': self.fv_mat.dtype})) # , 'byte_order': self.byte_order

    def save_as_memmap(self, fname):
        # if fname exsits it is overwritten, otherwise it will be created
        with zipfile.ZipFile(fname, mode='w') as zf:
            # perhaps better write to a file and add this to the archive because tobytes makes a copy
            zf.writestr('efms.bin', self.fv_mat.tobytes(order='F'))
            self.write_efm_info(zf, 0)

    def clear(self):
        self.fv_mat = numpy.zeros((0, 0))
        self.reac_id.clear() 

# the class below could be used to open a efmtool binary-doubles file as memory map
# instead of saving into a zip file a npz file could also be used as this can also be loaded as memory map (wonder how they resolve decrompession while keeping the file on disk...)
class FluxVectorMemmap(FluxVectorContainer):
    def __init__(self, fname, shape=None, reac_id=None, offset=0, containing_temp_dir=None): # make offset always 13?
        # fname is either a ZIP or an efmtool binary-doubles file (Java, big endian)
        # if it is a binary-doubles file shape, reac_id, offset must be correctly specified
        if zipfile.is_zipfile(fname):
            self._containing_temp_dir = tempfile.TemporaryDirectory()
            with zipfile.ZipFile(fname) as zf:
                zf.extractall(self._containing_temp_dir.name)
            self._memmap_fname = os.path.join(self._containing_temp_dir.name, 'efms.bin')
            with open(os.path.join(self._containing_temp_dir.name, 'efm_info'), 'rb') as fh:
                efm_info = pickle.load(fh)
            shape = (efm_info['num_reac'], efm_info['num_efm'])
            # offset = 13
            self.reac_id = efm_info['reac_id']
            # self.byte_order = efm_info['byte_order']
            # if self.byte_order == 'big':
            #     memmap_dtype = '>d'
            # else:
            #     memmap_dtype = '<d'
            memmap_dtype = efm_info['dtype']
            offset = efm_info['offset']
        else:
            # self.byte_order = 'big'
            if containing_temp_dir is not None:
                self._containing_temp_dir = containing_temp_dir # keep the temporary directory alive
                self._memmap_fname = os.path.join(containing_temp_dir.name, fname)
            else:
                self._memmap_fname = fname
                self._containing_temp_dir = None
            memmap_dtype = '>d'
            offset = 13
        super().__init__(numpy.memmap(self._memmap_fname, mode='r', dtype=memmap_dtype, offset=offset, shape=shape, order='F'), reac_id)

    def save(self, fname):
        # if fname exsits it is overwritten, otherwise it will be created
        with zipfile.ZipFile(fname, mode='w') as zf:
            zf.write(self._memmap_fname, arcname='efms.bin')
            # zf.writestr('efm_info', pickle.dumps({'num_reac': self.fv_mat.shape[0], 'num_efm': self.fv_mat.shape[1], 'reac_id': self.reac_id}))
            self.write_efm_info(zf, 13)

    def clear(self):
        del self.fv_mat # lose the reference to the memmap (does not have a close() method)
        self.fv_mat = None 
        self._containing_temp_dir = None # if this was the last reference to the temporary directory it is now deleted
        super().clear()

    def __del__(self):
        del self.fv_mat # lose the reference to the memmap so that the later implicit deletion of the temporary directory can proceed without problems
        

# %%
