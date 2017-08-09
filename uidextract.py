#!/usr/bin/python3
import sys
import os
import re
import json
import argparse
import functools

import requests
from requests.packages.urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

description = '''
Save a local copy of your openmailbox emails without using IMAP

csrfcookie and sessionid are the two cookies use by the webmail

Note that you can only download a maximum of 500 messages each time you run this script. So, if you have more than 500 messages in a folder, you will have to run it multiple times, changing the upperbound and lowerbound values on each run.
'''

@functools.wraps(print)
def dlog(*args, **kw):
    if debug:
        print(*args, **kw)

@functools.wraps(print)
def elog(*args, **kw):
    print('\n', *args, '\n', **kw)
    exit(1)

def update_conf(s, csrfcookie, sessionid):
    with open('.uidconf', 'w') as f:
        json.dump({'new':[s.cookies['csrftoken'],s.cookies['sessionid']],'old':[csrfcookie, sessionid]}, f)

def setup(csrfcookie=None, sessionid=None):
    # Create a session object from requests library
    s = requests.Session()
    retries = Retry(total=10, backoff_factor=1,
                    status_forcelist=[500, 502, 504])
    s.mount('https://', HTTPAdapter(max_retries=retries))
    if csrfcookie and sessionid:
        s.headers.update({'Cookie': 'csrftoken={0};sessionid={1}'.format(csrfcookie, sessionid)})

    return s

def login(domain, name, password):
    s = setup()
    if domain and name and password:
        print('Logging in using name and password')
        csrftoken = extract_csrftoken_and_set(s, 'https://app.openmailbox.org/login')

        r = s.post('https://app.openmailbox.org/requests/guest', data={
               'domain':domain,
               'name':name,
               'password':password,
               'action':'login'
               })

        if r.status_code == 200:
            return s
        elif r.status_code == 400:
            e = r.json()
            elog(e['exception'], e['error_info'])
        else:
            elog('Something went wrong', r.text)
    else:
        if not domain and not name and not password:
            elog('no account specify, unable to continue')
        elif not domain:
            elog('missing domain, unable to continue')
        elif not name:
            elog('missing name, unable to continue')
        elif not password:
            elog('missing password, unable to continue')

def get_inboxes(s):
    mdatareq = 'https://app.openmailbox.org/requests/webmail?action=folderlist'
    dlog(mdatareq)

    folderdata = json.loads(s.get(mdatareq).text)
    dlog(folderdata)

    return folderdata

def extract_folder_name(folderdata):
    return [folder['name'] for folder in folderdata['folders']]

def extract_csrftoken_and_set(s, link):
    csrftoken = re.search('<meta name="csrf-token" content="(.+?)">', s.get(link).text).group(1)
    s.headers.update({'X-CSRFToken':csrftoken})
    dlog(csrftoken)

def print_inboxes(foldernames):
    
    print('Available folders: ')
    print('\n'.join('\t'+name for name in foldernames))

def get_emails(s, mailbox, lowerbound, upperbound, trash=False, delete=False):
    print("Getting list of emails")

    foldernames = extract_folder_name(get_inboxes(s))

    # check if mailbox exists
    if not mailbox in foldernames:
        print('Available folders:\n')
        print(print_inboxes(foldernames))
        elog('No such folder:', mailbox)

    mdatareq = 'https://app.openmailbox.org/requests/webmail?range={0}-{1}&sort=date&order=0&selected=&action=maillist&mailbox={2}'.format(lowerbound, upperbound, mailbox)
    dlog(mdatareq)

    metadata = json.loads(s.get(mdatareq).text)
    dlog(metadata)

    uids = []
    for line in metadata['partial_list']:
        uids.append(line['uid'])
    print("Finished getting list of emails")

    # get csrftoken require for modifiying mailbox (move and delete)
    csrftoken = extract_csrftoken_and_set(s, 'https://app.openmailbox.org/webmail/')

    os.makedirs('emails_output_dir', exist_ok=True)
    print("Created directory emails_output_dir if it didn't already exist")

    for uid in uids:
        fname = 'emails_output_dir/' + str(mailbox) + '-' + str(uid) + ".eml"
        if not os.path.isfile(fname):
            req = 'https://app.openmailbox.org/requests/webmail?mailbox={0}&uid={1}&action=downloadmessage'.format(mailbox, str(uid))
            resp = s.get(req, stream=True)
            with open(fname, 'wb') as eml:
                for chunk in resp:
                    eml.write(chunk)
            print("Saved message " + fname)
        else:
            print("Already downloaded " + str(uid))
            if trash or delete:
                if stop_on_existing:
                    elog('Exiting incase of false postive (id reuse)')
                else:
                    print('Stopping trash and deletion incase of false postive (id reuse)')
                    trash = delete = False

        if not trash and not delete: continue

        # move 'downloaded' mail from inbox to trash require by webmail for deletion
        r = s.post('https://app.openmailbox.org/requests/webmail',
                   data={'action':'move', 'mailbox':mailbox, 'dest':'Trash', 'uids':uid}
                   )

        result = r.json()
        if not 'success' in result:
            raise Exception('something wrong:', result)

        print("Moved message " + str(uid) + " to trash")

    if not delete: exit(0)

    print("Getting list of trash for autodeletion")

    mdatareq = 'https://app.openmailbox.org/requests/webmail?range=1-500&sort=date&order=0&selected=&action=maillist&mailbox=Trash'
    dlog(mdatareq)

    metadata = json.loads(s.get(mdatareq).text)
    dlog(metadata)

    trash_uids = []
    for line in metadata['partial_list']:
        trash_uids.append(line['uid'])
    print("Finished getting list of trash")

    # delete all mail in trash
    for uid in trash_uids:
        r = s.post('https://app.openmailbox.org/requests/webmail',
                   data={'action':'deletemessage', 'mailbox':'Trash', 'uids':uid}
                   )
        dlog(r.text)

        result = r.json()

        if not 'success' in result:
            raise Exception('something wrong:', result)

        print("Deleted message " + str(uid))

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=description, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('csrfcookie', nargs='?', type=str)
    parser.add_argument('sessionid', nargs='?', type=str)
    parser.add_argument('mailbox', nargs='?', type=str, default='INBOX', help='The mailbox to download from')
    parser.add_argument('lowerbound', nargs='?', type=int, default=1)
    parser.add_argument('upperbound', nargs='?', type=int, default=500)
    parser.add_argument('-m','--mailbox', dest='mailbox2', type=str, help='The mailbox to download from')
    parser.add_argument('-b','--bound', nargs=2, type=int, help='The lower and upper bound')
    parser.add_argument('-n','--name', type=str, help='Email address/name')
    parser.add_argument('-D','--domain', type=str, help='Domain, if not provided, assume it is in the address')
    parser.add_argument('-p','--password', type=str, help='Email password')
    parser.add_argument('-t','--trash', action='store_true', help='Auto trash downloaded mail')
    parser.add_argument('-d','--delete', action='store_true', help='Auto delete downloaded mail')
    parser.add_argument('-v','--debug', action='count', help='print out more info', default=0)
    parser.add_argument('-l','--list', action='store_true', help='List your mailboxes (folders) and exit')
    parser.add_argument('--dontexitonfirstsignoftrouble', dest='stop_on_existing', action='store_false')

    args = parser.parse_args()

    debug = args.debug
    stop_on_existing = args.stop_on_existing
    csrfcookie = args.csrfcookie
    sessionid = args.sessionid

    # prioritize dash args
    mailbox = args.mailbox2 if args.mailbox2 is not None else args.mailbox
    lowerbound, upperbound = args.bound if args.bound is not None else args.lowerbound, args.upperbound

    if not args.domain and args.name:
        if '@' in args.name:
            args.name, args.domain = args.name.split("@")
        else:
            elog("Domain not specify and name doesn't contain @")

    if os.path.isfile('.uidconf'):
        try:
            with open('.uidconf') as f:
                conf = json.load(f)
                if set(conf['old']) == {args.csrfcookie, args.sessionid}:
                    csrfcookie, sessionid = conf['new']
                    dlog()
                    dlog('Before','After')
                    dlog(args.csrfcookie, csrfcookie)
                    dlog(args.sessionid, sessionid)
                    dlog()
        except json.decoder.JSONDecodeError:
            dlog('Cookie cache corrupted, ignoring it')

    dlog(args)
    if args.debug >=2:
        exit(0)

    if csrfcookie and sessionid:
        s = setup(csrfcookie, sessionid)
        count = s.get('https://app.openmailbox.org/requests/webmail?action=unseenandcount').json()
        if 'error_info' in count:
            print('csrfcookie session has expired')
            csrfcookie = sessionid = None

    if not csrfcookie or not sessionid:
        s = login(args.domain, args.name, args.password)
        update_conf(s, args.csrfcookie, args.sessionid)
        count = s.get('https://app.openmailbox.org/requests/webmail?action=unseenandcount').json()

    print('There are %d mails with %d unseen' % (count['messages'], count['unseen']))

    if args.list:
        print()
        print_inboxes(extract_folder_name(get_inboxes(session)))
        exit(0)

    if count['messages'] == 0:
        print('Exiting because of 0 mail')
        exit(0)

    if upperbound <= lowerbound:
        elog("The lower bound must be less than the upper bound")
    if upperbound - lowerbound > 500:
        elog('The difference between the upper bound and the lower'
              'bound must be less than or equal to 500.')

    get_emails(s, mailbox, lowerbound, upperbound, args.trash, args.delete)
