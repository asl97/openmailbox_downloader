#!/usr/bin/python3
import sys
import os
import re
import json
import argparse
import functools
import itertools

import requests
from requests.packages.urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

class CustomHelpFormatter(argparse.RawDescriptionHelpFormatter):
    def _format_action_invocation(self, action):
        if not action.option_strings or action.nargs == 0:
            return super()._format_action_invocation(action)
        default = self._get_default_metavar_for_optional(action)
        args_string = self._format_args(action, default)
        return ', '.join(action.option_strings) + ' ' + args_string

description = '''
Save a local copy of your openmailbox emails without using IMAP

csrfcookie and sessionid are the two cookies use by the webmail

Note that you can only download a maximum of 500 messages each time you run this script unless --auto is use. So, if you have more than 500 messages in a folder, you will have to run it multiple times, changing the upperbound and lowerbound values on each run.
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
        s.headers.update({'Cookie': 'csrftoken={0};sessionid={1}'.format(csrfcookie, sessionid),
                          'Referer':'https://app.openmailbox.org/'})

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

    folderdata = s.get(mdatareq).json()
    dlog(folderdata)

    return folderdata

def extract_folder_name(folderdata):
    return [folder['name'] for folder in folderdata['folders']]

def extract_csrftoken_and_set(s, link):
    csrftoken = re.search('<meta name="csrf-token" content="(.+?)">', s.get(link).text).group(1)
    s.headers.update({'X-CSRFToken':csrftoken})
    dlog(csrftoken)

def print_inboxes(foldernames):
    print()
    print('Available folders: ')
    print('\n'.join('\t'+name for name in foldernames))

def print_mail(meta, print_info):
    dlog(meta, print_info)
    def _print_mail(item):
        dlog(item)
        if item == 'name' or item == 'email':
            return (item+':', meta['from'][0][item])
        else:
            return (item+':', meta[item])

    return itertools.chain.from_iterable(map(_print_mail, print_info))

def get_emails(s, mailbox, lowerbound, upperbound, trash=False, delete=False, auto=False, skip=False, print_info=[]):
    print("Getting list of emails")

    foldernames = extract_folder_name(get_inboxes(s))

    # check if mailbox exists
    if not mailbox in foldernames:
        print_inboxes(foldernames)
        elog('No such folder:', mailbox)

    mdatareq = 'https://app.openmailbox.org/requests/webmail?range={0}-{1}&sort=date&order=1&selected=&action=maillist&mailbox={2}'.format(lowerbound, upperbound, mailbox)
    dlog(mdatareq)

    metadata = s.get(mdatareq).json()
    dlog(metadata)

    print("Finished getting list of emails")

    # get csrftoken require for modifiying mailbox (move and delete)
    if trash or delete:
        csrftoken = extract_csrftoken_and_set(s, 'https://app.openmailbox.org/webmail/')

    os.makedirs('emails_output_dir', exist_ok=True)
    print("Created directory emails_output_dir if it didn't already exist")

    # Offset mail index by one so we shouldn't get the same mail twice
    diffbound = upperbound - lowerbound + 1

    while True:
        for meta in metadata['partial_list']:
            uid = meta['uid']
            fname = 'emails_output_dir/' + str(mailbox) + '-' + str(uid) + ".eml"
            if os.path.isfile(fname):
                if skip:
                    print("Skipped message", uid, "[id existing]")
                    continue
                i = 1
                while os.path.isfile(fname):
                    fname = 'emails_output_dir/' + str(mailbox) + '-' + str(uid) + " (%d)" % i + ".eml"
                    i += 1

            req = 'https://app.openmailbox.org/requests/webmail?mailbox={0}&uid={1}&action=downloadmessage'.format(mailbox, str(uid))
            resp = s.get(req, stream=True)
            with open(fname, 'wb') as eml:
                for chunk in resp:
                    eml.write(chunk)
            print("Saved message", fname, *print_mail(meta, print_info))

            if not trash and not delete: continue

            # move 'downloaded' mail from inbox to trash require by webmail for deletion
            r = s.post('https://app.openmailbox.org/requests/webmail',
                       data={'action':'move', 'mailbox':mailbox, 'dest':'Trash', 'uids':uid}
                       )

            result = r.json()
            if not 'success' in result:
                raise Exception('something wrong:', result)

            print("Moved message " + str(uid) + " to trash")

        if not auto:
            break

        # we assume the mail was moved out of the mailbox if trash or delete is set
        # so we just need to request the same bound again
        if not trash and not delete:
            upperbound += diffbound
            lowerbound += diffbound

        if metadata['total_mailbox_mail_count'] > 0 and not metadata['total_mailbox_mail_count'] < lowerbound:
            mdatareq = 'https://app.openmailbox.org/requests/webmail?range={0}-{1}&sort=date&order=1&selected=&action=maillist&mailbox={2}'.format(lowerbound, upperbound, mailbox)
            dlog(mdatareq)

            metadata = s.get(mdatareq).json()
            dlog(metadata)
        else:
            break

    if not delete: exit(0)

    print("Getting list of trash for autodeletion")

    mdatareq = 'https://app.openmailbox.org/requests/webmail?range=1-500&sort=date&order=1&selected=&action=maillist&mailbox=Trash'
    dlog(mdatareq)

    metadata = s.get(mdatareq).json()
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
    parser = argparse.ArgumentParser(description=description, formatter_class=CustomHelpFormatter)
    parser.add_argument('csrfcookie', nargs='?', type=str)
    parser.add_argument('sessionid', nargs='?', type=str)
    parser.add_argument('mailbox', nargs='?', type=str, default='INBOX', help='The mailbox to download from')
    parser.add_argument('lowerbound', nargs='?', type=int, default=1)
    parser.add_argument('upperbound', nargs='?', type=int, default=500)
    parser.add_argument('-m','--mailbox', metavar='INBOX', dest='mailbox2', type=str, help='The mailbox to download from')
    parser.add_argument('-b','--bound',  metavar=('lower', 'upper'), nargs=2, type=int, help='The lower and upper bound')
    parser.add_argument('-n','--name', metavar='example', type=str, help='Email address/name')
    parser.add_argument('-D','--domain', metavar='openmailbox.org', type=str, help='Domain, if not provided, assume it is in the address')
    parser.add_argument('-p','--password', metavar='secret', type=str, help='Email password')
    action_group = parser.add_argument_group('Mailbox Operators')
    action_group.add_argument('-l','--list', action='store_true', help='List your mailboxes (folders) and exit')
    action_group.add_argument('-S','--skip', action='store_true', help='Skip mail with existing id')
    action_group.add_argument('-a','--auto', action='store_true', help='Auto download all the mails')
    action_group.add_argument('-t','--trash', action='store_true', help='Auto trash downloaded mail')
    action_group.add_argument('-d','--delete', action='store_true', help='Auto delete downloaded mail')
    print_group = parser.add_argument_group('Mail Information', 'Print additional information when saving mails')
    print_group.add_argument('-s','--subject', dest='print_info', action='append_const', const='subject')
    print_group.add_argument('--attachment', dest='print_info', action='append_const', const='attachment')
    print_group.add_argument('--from-name', dest='print_info', action='append_const', const='name')
    print_group.add_argument('--from-email', dest='print_info', action='append_const', const='email')
    dev_group = parser.add_argument_group('Dev')
    dev_group.add_argument('-v','--debug', action='count', help='Print out more info', default=0)
    dev_group.add_argument('--donotexitonfirstsignoftrouble', action='store_false', dest='stop_on_existing', help='Do not stop even when something unexpected happens, WARNING: ACCIDENTAL DELETION MIGHT HAPPEN IF USE')

    args = parser.parse_args()

    debug = args.debug
    stop_on_existing = args.stop_on_existing
    csrfcookie = args.csrfcookie
    sessionid = args.sessionid

    if not args.name and not args.password and not args.csrfcookie and not args.sessionid:
        parser.print_help()
        exit(0)

    # prioritize dash args
    mailbox = args.mailbox2 if args.mailbox2 is not None else args.mailbox
    lowerbound, upperbound = args.bound if args.bound is not None else (args.lowerbound, args.upperbound)

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

    dlog(count)
    print('There are %d mails with %d unseen' % (count['messages'], count['unseen']))

    if args.list:
        print()
        print_inboxes(extract_folder_name(get_inboxes(s)))
        exit(0)

    if count['messages'] == 0:
        print('Exiting because of 0 mail')
        exit(0)

    if upperbound < lowerbound:
        elog("The lower bound must be less than or equal the upper bound")
    if upperbound - lowerbound > 500:
        elog('The difference between the upper bound and the lower'
              'bound must be less than or equal to 500.')

    get_emails(s, mailbox, lowerbound, upperbound, args.trash, args.delete, args.auto, args.skip, args.print_info)
