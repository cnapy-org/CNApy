import os
import subprocess


# python G:\CPLEX\CPLEX_Studio221\python\setup.py install
cplex_folder = "G:/CPLEX/CPLEX_Studio221/"
cplex_folder = cplex_folder.replace("\\", "/")
if not cplex_folder.endswith("/"):
    cplex_folder += "/"

if not os.path.isdir(cplex_folder):
    print("ERROR: Given CPLEX path does not exist. Please check that you chose the right folder in which you've installed CPLEX.")

cplex_python_file = cplex_folder + "python/setup.py"
if not os.path.isfile(cplex_python_file):
    print("ERROR: CPLEX setup.py does not exist. Please check that you use a recent CPLEX version (not older than version 22.10). CNApy isn't compatible with older CPLEX versions.")

has_error = subprocess.check_call("python " + cplex_python_file + " install")

if has_error:
    print("ERROR: CPLEX's setup.py run failed! Please check that you use a recent CPLEX version (not older than version 22.10). CNApy isn't compatible with older CPLEX versions.")
else:
    pythonpath = cplex_folder + "cplex/python/3.8/x64_win64"
    print(
        f"SUCCESS! Now, you have to set an environmental variable called PYTHONPATH to the path {pythonpath}")
    print("Please consult your current operating system's (e.g., Windows or Linux) manual in order to find out how you can set an environmental variable.")
    print("Then, please restart your computer in order to use CNApy with CPLEX.")
