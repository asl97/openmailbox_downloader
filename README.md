# openmailbox_downloader
Save a local copy of your openmailbox emails without using IMAP

## Motivation
On 5th August 2017, [openmailbox.org](https://openmailbox.org) changed its service by requiring people to pay for IMAP. No warning was given for this, and I have not been able to find a simple way to download all of my emails from the server.

## Dependencies
For this tool to work, you need to install Python 3, and the module listed in requirements.txt.

If you have pip installed, you can do this with the command:
`pip3 install -r requirements.txt`

## How this tool works

#### The original way:
To use this tool, you need to [log in to openmailbox's webmail](https://app.openmailbox.org/login).

Then, you will need to view the cookies that openmailbox has put on your computer. In particular, you will need to find the _sessionid_ and the _csrftoken_.

Then, you need to run this command:

`./uidextract.py <csrftoken> <sessionid> [mailbox] [lowerbound] [upperbound]`

where _csrftoken_ and _sessionid_ are the two cookies you found earlier, mailbox is the folder you want to download from (default to 'INBOX') and lowerbound and upperbound are the lowest and highest number messages you want respectively.

#### The new way
Provide your email address and password and it will login and get the cookies for you.

The address and password will only be use to retrieve the cookies, you can check the source to verify it.

The command:

`./uidextract.py --name <example@openmailbox.org> --password <secret> --mailbox <INBOX> --bound <lower> <upper>`

or

`./uidextract.py --name <example> --domain <openmailbox.org> --password <secret> --mailbox <INBOX> --bound <lower> <upper>`

#### Other information
You can list your mailboxes (folders) using this command:

`./uidextract.py --list <csrftoken> <sessionid>`

There is an inbuilt help menu which is shown when running this command:

`./uidextract.py --help`

Output as of 63f1e61948bf7c5183c356ef07df7fd39212dbbb
```
usage: uidextract.py [-h] [-m INBOX] [-b lower upper] [-n example]
                     [-D openmailbox.org] [-p secret] [-l] [-a] [-t] [-d] [-s]
                     [--attachment] [--from-name] [--from-email] [-v]
                     [--donotexitonfirstsignoftrouble]
                     [csrfcookie] [sessionid] [mailbox] [lowerbound]
                     [upperbound]

Save a local copy of your openmailbox emails without using IMAP

csrfcookie and sessionid are the two cookies use by the webmail

Note that you can only download a maximum of 500 messages each time you run this script. So, if you have more than 500 messages in a folder, you will have to run it multiple times, changing the upperbound and lowerbound values on each run.

positional arguments:
  csrfcookie
  sessionid
  mailbox               The mailbox to download from
  lowerbound
  upperbound

optional arguments:
  -h, --help            show this help message and exit
  -m, --mailbox INBOX   The mailbox to download from
  -b, --bound lower upper
                        The lower and upper bound
  -n, --name example    Email address/name
  -D, --domain openmailbox.org
                        Domain, if not provided, assume it is in the address
  -p, --password secret
                        Email password

Mailbox Operators:
  -l, --list            List your mailboxes (folders) and exit
  -a, --auto            Auto download all the mails
  -t, --trash           Auto trash downloaded mail
  -d, --delete          Auto delete downloaded mail

Mail Information:
  Print additional information when saving mails

  -s, --subject
  --attachment
  --from-name
  --from-email

Dev:
  -v, --debug           Print out more info
  --donotexitonfirstsignoftrouble
                        Do not stop even when something unexpected happens,
                        WARNING: ACCIDENTAL DELETION MIGHT HAPPEN IF USE
```

The saved emails will be in the folder `emails_output_dir`.  The format will be `<mailbox_name>-<uid>.eml`.

If the script gets interrupted, the script tries to avoid redownload emails that you have already downloaded.

## Examples

`./uidextract.py eri17r6toiughw3rtg9bv3qcf8o34nqt9y n9o34yqto783bn34yrf3cyo834ytn843qtc3hvukerhgliurhgoi243 INBOX 1 500`

Downloads the first 500 messages from INBOX
