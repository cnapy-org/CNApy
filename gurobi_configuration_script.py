import os
import subprocess


gurobi_folder = "G:/gurobi/gurobi_Studio221/"
gurobi_folder = gurobi_folder.replace("\\", "/")
if not gurobi_folder.endswith("/"):
    gurobi_folder += "/"

if not os.path.isdir(gurobi_folder):
    print("ERROR: Given Gurobi path does not exist. Please check that you chose the right folder in which you've installed Gurobi.")

gurobi_python_file = gurobi_folder + "setup.py"
if not os.path.isfile(gurobi_python_file):
    print("ERROR: Gurobi setup.py does not exist. Please check that you use a recent Gurobi version . CNApy isn't compatible with older Gurobi versions.")

has_error = subprocess.check_call("python " + gurobi_python_file + " install")

if has_error:
    print("ERROR: Gurobi's setup.py run failed! Please check that you use a recent gurobi version. CNApy isn't compatible with older Gurobi versions.")
else:
    pythonpath = gurobi_folder + "gurobi/python/3.8/x64_win64"
    print("SUCCESS!")
    print("Please restart your computer in order to use CNApy with Gurobi.")
