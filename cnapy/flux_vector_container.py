import os
import numpy
from qtpy.QtWidgets import QMessageBox


class FluxVectorContainer:
    def __init__(self, matORfname, reac_id=None, irreversible=None, unbounded=None):
        if type(matORfname) is str:
            try:
                l = numpy.load(matORfname, allow_pickle=True)  # allow_pickle to read back sparse matrices saved as fv_mat
                self.fv_mat = l['fv_mat']
            except Exception:
                QMessageBox.critical(
                    None,
                    'Could not open file',
                    "File could not be opened as it does not seem to be a valid EFM file. "
                    "Maybe the file got the .npz ending for other reasons than being a scenario file or the file is corrupted."
                )
                return
            if self.fv_mat.dtype == numpy.object: # in this case assume fv_mat is scipy.sparse
                self.fv_mat = self.fv_mat.tolist() # not sure why this works...
            self.reac_id = l['reac_id'].tolist()
            self.irreversible = l['irreversible']
            self.unbounded = l['unbounded']
        else:
            if reac_id is None:
                raise TypeError('reac_id must be provided')
            self.fv_mat = matORfname  # each flux vector is a row in fv_mat
            self.reac_id = reac_id  # corresponds to the columns of fv_mat
            if irreversible is None:
                self.irreversible = numpy.array(0)
            else:
                self.irreversible = irreversible
            if unbounded is None:
                self.unbounded = numpy.array(0)
            else:
                self.unbounded = unbounded

    def __len__(self):
        return self.fv_mat.shape[0]

    def is_integer_vector_rounded(self, idx, decimals=0):
        # TODO: does not yet work when fv_mat is list of lists sparse matrix
        # return all([val.is_integer() for val in numpy.round(self.fv_mat[idx, :], decimals)])
        return all(round(val, decimals).is_integer() for val in self.fv_mat[idx, :])

    def __getitem__(self, idx):
        return{self.reac_id[i]: float(self.fv_mat[idx, i]) for i in range(len(self.reac_id)) if self.fv_mat[idx, i] != 0}

    def save(self, fname):
        numpy.savez_compressed(fname, fv_mat=self.fv_mat, reac_id=self.reac_id, irreversible=self.irreversible,
                               unbounded=self.unbounded)

    def clear(self):
        self.fv_mat = numpy.zeros((0, 0))
        self.reac_id = []
        self.irreversible = numpy.array(0)
        self.unbounded = numpy.array(0)


class FluxVectorMemmap(FluxVectorContainer):
    '''
    This class can be used to open an efmtool binary-doubles file directly as a memory map
    '''

    def __init__(self, fname, reac_id, containing_temp_dir=None):
        if containing_temp_dir is not None:
            # keep the temporary directory alive
            self._containing_temp_dir = containing_temp_dir
            self._memmap_fname = os.path.join(containing_temp_dir.name, fname)
        else:
            self._memmap_fname = fname
            self._containing_temp_dir = None
        with open(self._memmap_fname, 'rb') as fh:
            num_efm = numpy.fromfile(fh, dtype='>i8', count=1)[0]
            num_reac = numpy.fromfile(fh, dtype='>i4', count=1)[0]
        super().__init__(numpy.memmap(self._memmap_fname, mode='r+', dtype='>d',
                                      offset=13, shape=(num_efm, num_reac), order='C'), reac_id)

    def clear(self):
        # lose the reference to the memmap (does not have a close() method)
        del self.fv_mat
        super().clear()
        # if this was the last reference to the temporary directory it is now deleted
        self._containing_temp_dir = None

    def __del__(self):
        del self.fv_mat  # lose the reference to the memmap so that the later implicit deletion of the temporary directory can proceed without problems
