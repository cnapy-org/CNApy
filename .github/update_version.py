import re
import sys
file_i = sys.argv[1]
version = sys.argv[2]

with open (file_i, 'r' ) as f:
    content = f.read()
    content_new = re.sub(r"(?<=version\=').*?(?=')", str(version), content, flags = re.M)
    content_new = re.sub(r"(?<=version \= ').*?(?=')", str(version), content_new, flags = re.M)
    content_new = re.sub(r"(?<=version:).*?(?=(\n|$))", str(version), content_new, flags = re.M)
    content_new = re.sub(r'(?<=self\.version = "cnapy-).*?(?=("))', str(version), content_new, flags = re.M)
    content_new = re.sub(r'(?<=call mamba install cnapy\=).*?(?=( -c))', str(version), content_new, flags = re.M)
    # replace in Readme:
    content_new = re.sub(r"(?<=conda create -n cnapy-).*?(?=( -c))", str(version), content_new, flags = re.M)
    content_new = re.sub(r"(?<=conda-forge -c cnapy cnapy\=).*?(?=($|\n|\s))", str(version), content_new, flags = re.M)
    content_new = re.sub(r"(?<=conda activate cnapy-).*?(?=($|\n|\s))", str(version), content_new, flags = re.M)
with open (file_i, 'w' ) as f:
    f.write(content_new)
