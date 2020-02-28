try:
    import matlab.engine
    eng = matlab.engine.start_matlab()
    me = True
except:
    print("Matlab engine not found")
    me = False


def matlabcall():
    if me:
        tf = eng.isprime(37)
        print(tf)
        return tf
