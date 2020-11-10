import io
from abc import ABC, abstractmethod
try:
    import matlab.engine
except:
    print('Matlab engine not available.')

try:
    import oct2py
except:
    print('Octave is not available.')

a=42

class Mengine(ABC): # besser CNA_MEngine
    def __init__(self):
        self.out= io.StringIO() #only for Matlab?
        self.err= io.StringIO()
        self.eng= None
    # abstract method 
    def eval(self): 
        pass

    def cd(self, dir):
        self.eng.cd(dir)

    def load(self, matfile):
        self.eng.eval('load '+matfile, nargout=0)
  
class MatlabEngine(Mengine):
    def __init__(self):
        super().__init__()
        try:
            self.eng= matlab.engine.start_matlab()
        except:
            self.eng= None

    # overriding abstract method 
    def eval(self): 
        print("I have 3 sides")

class OctaveEngine(Mengine):

    def __init__(self):
        super().__init__()
        try:
            self.eng= oct2py.Oct2Py()
        except:
            self.eng= None

    # overriding abstract method 
    def eval(self): 
        print("I have 3 sides")

# class CNA_Mengine():
#     def __init__(self, Mengine: eng):
#         self.eng= eng

