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


def save_request(uuid, request, printable=False):
    req_data = {}
    req_data['uuid'] = uuid
    req_data['endpoint'] = request.endpoint
    req_data['method'] = request.method
    req_data['cookies'] = request.cookies
    req_data['data'] = request.data
    req_data['headers'] = dict(request.headers)
    req_data['headers'].pop('Cookie', None)
    req_data['args'] = request.args
    req_data['form'] = request.form
    req_data['remote_addr'] = request.remote_addr
    if printable:
        req_data['data'] = req_data['data'].decode('utf-8')
    return req_data
