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

csrftoken and sessionid are the two cookies use by the webmail
TODO: figure out login so we can get them since those cookie don't stay vaild for long

Note that you can only download a maximum of 500 messages each time you run this script. So, if you have more than 500 messages in a folder, you will have to run it multiple times, changing the upperbound and lowerbound values on each run.
'''

@functools.wraps(print)
def dlog(*args, **kw):
    if debug:
        print(*args, **kw)

def setup(csrftoken, sessionid):
    # Create a session object from requests library
    s = requests.Session()
    retries = Retry(total=10, backoff_factor=1,
                    status_forcelist=[500, 502, 504])
    s.mount('https://', HTTPAdapter(max_retries=retries))
    s.headers.update({'Cookie': 'csrftoken={0};sessionid={1}'.format(csrftoken, sessionid)})

    return s

def get_inboxes(s):
    mdatareq = 'https://app.openmailbox.org/requests/webmail?action=folderlist'
    dlog(mdatareq)

    folderdata = json.loads(s.get(mdatareq).text)
    dlog(folderdata)

    return folderdata

def extract_folder_name(folderdata):
    return [folder['name'] for folder in folderdata['folders']]

def print_inboxes(foldernames):
    
    print('Available folders: ')
    print('\n'.join('\t'+name for name in foldernames))

def get_emails(s, mailbox, lowerbound, upperbound, trash=False, delete=False):
    print("Getting list of emails")

    foldernames = extract_folder_name(get_inboxes(s))

    # check if mailbox exists
    if not mailbox in foldernames:
        print('no such folder:', mailbox,'\n')
        print(print_inboxes(foldernames))
        exit(1)

    mdatareq = 'https://app.openmailbox.org/requests/webmail?range={0}-{1}&sort=date&order=0&selected=&action=maillist&mailbox={2}'.format(lowerbound, upperbound, mailbox)
    dlog(mdatareq)

    metadata = json.loads(s.get(mdatareq).text)
    dlog(metadata)

    uids = []
    for line in metadata['partial_list']:
        uids.append(line['uid'])
    print("Finished getting list of emails")

    # get csrftoken require for modifiying mailbox (move and delete)
    csrftoken = re.search('<meta name="csrf-token" content="(.+?)">', s.get('https://app.openmailbox.org/webmail/').text).group(1)
    dlog(csrftoken)

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
                    print('Exiting incase of false postive (id reuse)')
                    exit(1)
                else:
                    print('Stopping trash and deletion incase of false postive (id reuse)')
                    trash = delete = False

        if not trash and not delete: continue

        # move 'downloaded' mail from inbox to trash require by webmail for deletion
        r = s.post('https://app.openmailbox.org/requests/webmail',
                   data={'action':'move', 'mailbox':mailbox, 'dest':'Trash', 'uids':uid},
                   headers={'X-CSRFToken': csrftoken}
                   )

        result = r.json()
        if not 'success' in result:
            raise Exception('something wrong:', result)

        print("Moved message " + str(uid) + "to trash")

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
                   data={'action':'deletemessage', 'mailbox':'Trash', 'uids':uid},
                   headers={'X-CSRFToken': csrftoken}
                   )
        dlog(r.text)

        result = r.json()

        if not 'success' in result:
            raise Exception('something wrong:', result)

        print("Deleted message " + str(uid))

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=description, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('csrftoken', type=str)
    parser.add_argument('sessionid', type=str)
    parser.add_argument('mailbox', nargs='?', type=str, default='INBOX', help='The mailbox to download from')
    parser.add_argument('lowerbound', nargs='?', type=int, default=1)
    parser.add_argument('upperbound', nargs='?', type=int, default=500)
    parser.add_argument('-t','--trash', action='store_true', help='Auto trash downloaded mail')
    parser.add_argument('-d','--delete', action='store_true', help='Auto delete downloaded mail')
    parser.add_argument('-v','--debug', action='store_true', help='print out more info')
    parser.add_argument('-l','--list', action='store_true', help='List your mailboxes (folders) and exit')
    parser.add_argument('--dontexitonfirstsignoftrouble', dest='stop_on_existing', action='store_false')

    args = parser.parse_args()

    debug = args.debug
    stop_on_existing = args.stop_on_existing

    dlog(args)

    session = setup(args.csrftoken, args.sessionid)

    if args.list:
        print()
        print_inboxes(extract_folder_name(get_inboxes(session)))
        exit(0)

    if args.upperbound <= args.lowerbound:
        print("The lower bound must be less than the upper bound")
        exit()
    if args.upperbound - args.lowerbound > 500:
        print('The difference between the upper bound and the lower'
              'bound must be less than or equal to 500.')
        exit()

    get_emails(session, args.mailbox, args.lowerbound, args.upperbound, args.trash, args.delete)
