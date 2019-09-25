def download(url, folder, basename=None, headers={}):
    """Download a file to a local folder.

    Args:
        url (str): URL of the file to download
        folder (str): Path to a local folder to download the file to
        basename (str, optional): Name of the downloaded file, excluding extension
        headers (dict, optional): Headers to use for the request

    Required packages: furl, requests

    `pip install -U furl requests`
    """
    import shutil
    import os
    import furl
    import requests
    url_f = furl.furl(url).remove(query=True, fragment=True)
    r = requests.get(url_f.url, stream=True, headers=headers)
    if r.status_code != requests.codes['ok']:
        raise Exception('Request failed: {0} {1}'
                        .format(r.status_code, r.reason))
    else:
        os.makedirs(folder, exist_ok=True)
        filename = ('{0}{1}'.format(basename, os.path.splitext(url_f.url)[1])
                    if basename
                    else url_f.path.segments[-1])
        localfile = os.path.join(folder, filename)
        with open(localfile, 'wb') as out_file:
            shutil.copyfileobj(r.raw, out_file)
