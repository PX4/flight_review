import requests

db_info_api = "http://localhost:5006/dbinfo"
download_api = "http://localhost:5006/download"
path_for_logfiles = "data/"

# the db_info_api sends a json file with a list of all public database entries
db_entries_list = requests.get(url=db_info_api).json()

print('First db entry:')
print(db_entries_list[0])

# download the first entry in the list using the log id and the download api
log_id = db_entries_list[0]['log_id']
file_path = path_for_logfiles+log_id+".ulg"

print("Download first db entry.")
r = requests.get(url=download_api+"?log="+log_id, stream=True)
with open(file_path, 'wb') as f:
    for chunk in r.iter_content(chunk_size=1024):
        if chunk: # filter out keep-alive new chunks
            f.write(chunk)

print("File saved to: " + file_path)