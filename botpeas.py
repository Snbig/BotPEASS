import requests
import datetime
import pathlib
import json
import os
import yaml
import vulners
import urllib.parse

from os.path import join
from enum import Enum
from discord import Webhook, RequestsWebhookAdapter


CIRCL_LU_URL = "https://cve.circl.lu/api/query"
CVES_JSON_PATH = join(pathlib.Path(__file__).parent.absolute(), "output/botpeas.json")
LAST_NEW_CVE = datetime.datetime.now() - datetime.timedelta(days=1)
LAST_MODIFIED_CVE = datetime.datetime.now() - datetime.timedelta(days=1)
TIME_FORMAT = "%Y-%m-%dT%H:%M:%S"

KEYWORDS_CONFIG_PATH = join(pathlib.Path(__file__).parent.absolute(), "config/botpeas.yaml")
ALL_VALID = False
DESCRIPTION_KEYWORDS_I = []
DESCRIPTION_KEYWORDS = []
PRODUCT_KEYWORDS_I = []
PRODUCT_KEYWORDS = []


class Time_Type(Enum):
    PUBLISHED = "Published"
    LAST_MODIFIED = "last-modified"

cwe_data = {}

################## LOAD CONFIGURATIONS ####################

def load_keywords():
    ''' Load keywords from config file '''

    with open("config/cwe_data.json", 'r', encoding='utf-8') as file:
        cwe_data = json.load(file)

    global ALL_VALID
    global DESCRIPTION_KEYWORDS_I, DESCRIPTION_KEYWORDS
    global PRODUCT_KEYWORDS_I, PRODUCT_KEYWORDS

    with open(KEYWORDS_CONFIG_PATH, 'r') as yaml_file:
        keywords_config = yaml.safe_load(yaml_file)
        print(f"Loaded keywords: {keywords_config}")
        ALL_VALID = keywords_config["ALL_VALID"]
        DESCRIPTION_KEYWORDS_I = keywords_config["DESCRIPTION_KEYWORDS_I"]
        DESCRIPTION_KEYWORDS = keywords_config["DESCRIPTION_KEYWORDS"]
        PRODUCT_KEYWORDS_I = keywords_config["PRODUCT_KEYWORDS_I"]
        PRODUCT_KEYWORDS = keywords_config["PRODUCT_KEYWORDS"]


def load_lasttimes():
    ''' Load lasttimes from json file '''

    global LAST_NEW_CVE, LAST_MODIFIED_CVE

    try:
        with open(CVES_JSON_PATH, 'r') as json_file:
            cves_time = json.load(json_file)
            LAST_NEW_CVE = datetime.datetime.strptime(cves_time["LAST_NEW_CVE"], TIME_FORMAT)
            LAST_MODIFIED_CVE = datetime.datetime.strptime(cves_time["LAST_MODIFIED_CVE"], TIME_FORMAT)

    except Exception as e: #If error, just keep the fault date (today - 1 day)
        print(f"ERROR, using default last times.\n{e}")
        pass

    print(f"Last new cve: {LAST_NEW_CVE}")
    print(f"Last modified cve: {LAST_MODIFIED_CVE}")


def update_lasttimes():
    ''' Save lasttimes in json file '''

    with open(CVES_JSON_PATH, 'w') as json_file:
        json.dump({
            "LAST_NEW_CVE": LAST_NEW_CVE.strftime(TIME_FORMAT),
            "LAST_MODIFIED_CVE": LAST_MODIFIED_CVE.strftime(TIME_FORMAT),
        }, json_file)



################## SEARCH CVES ####################

def get_cves(tt_filter:Time_Type) -> dict:
    ''' Given the headers for the API retrive CVEs from cve.circl.lu '''
    now = datetime.datetime.now() - datetime.timedelta(days=1)
    now_str = now.strftime("%d-%m-%Y")

    headers = {
        "time_modifier": "from",
        "time_start": now_str,
        "time_type": tt_filter.value,
        "limit": "100",
    }

    try:
        r = requests.get(CIRCL_LU_URL, headers=headers)
        r.raise_for_status()
    except requests.Timeout:
        print("Timeout occurred. Closing the program.")
        exit()
    except requests.RequestException as e:
        print("An error occurred:", e)
        exit()
    except requests.exceptions.ConnectionError as e:
        print("Connection error occurred:", e)
        exit()
    except requests.exceptions.ProtocolError as e:
        print("Protocol error occurred:", e)
        exit()
    except requests.exceptions.RequestException as e:
        print("An error occurred:", e)
        exit()
    return r.json()


def get_new_cves() -> list:
    ''' Get CVEs that are new '''

    global LAST_NEW_CVE

    cves = get_cves(Time_Type.PUBLISHED)
    filtered_cves, new_last_time = filter_cves(
            cves["results"],
            LAST_NEW_CVE,
            Time_Type.PUBLISHED
        )
    LAST_NEW_CVE = new_last_time

    return filtered_cves


def get_modified_cves() -> list:
    ''' Get CVEs that has been modified '''

    global LAST_MODIFIED_CVE

    cves = get_cves(Time_Type.LAST_MODIFIED)
    filtered_cves, new_last_time = filter_cves(
            cves["results"],
            LAST_MODIFIED_CVE,
            Time_Type.PUBLISHED
        )
    LAST_MODIFIED_CVE = new_last_time

    return filtered_cves


def filter_cves(cves: list, last_time: datetime.datetime, tt_filter: Time_Type) -> list:
    ''' Filter by time the given list of CVEs '''

    filtered_cves = []
    new_last_time = last_time

    for cve in cves:
        cve_time = datetime.datetime.strptime(cve[tt_filter.value], TIME_FORMAT)
        if cve_time > last_time:
            if ALL_VALID or is_summ_keyword_present(cve["summary"]) or is_prod_keyword_present(str(cve["vulnerable_configuration"])):
                if(is_summ_keyword_present(cve["summary"])) : cve['keyword'] = is_summ_keyword_present(cve["summary"])
                if(is_prod_keyword_present(str(cve["vulnerable_configuration"]))) : cve['keyword'] = is_prod_keyword_present(str(cve["vulnerable_configuration"]))
                filtered_cves.append(cve)

        if cve_time > new_last_time:
            new_last_time = cve_time

    return filtered_cves, new_last_time


def is_summ_keyword_present(summary: str):
    ''' Given the summary check if any keyword is present '''

    for w in DESCRIPTION_KEYWORDS:
        if w in summary:
            return w

    for w in DESCRIPTION_KEYWORDS_I:
        if w.lower() in summary.lower():
            return w
    return ''


def is_prod_keyword_present(products: str):
    ''' Given the summary find if any keyword is present '''
    
    for w in PRODUCT_KEYWORDS:
        if w in products:
            return w
    for w in PRODUCT_KEYWORDS_I:
        if w.lower() in products.lower():
            return w.lower()
    
    return ''  # Return empty string if no keyword found


def search_exploits(cve: str) -> list:
    ''' Given a CVE it will search for public exploits to abuse it '''
    
    return []
    #TODO: Find a better way to discover exploits

    vulners_api_key = os.getenv('VULNERS_API_KEY')
    
    if vulners_api_key:
        vulners_api = vulners.Vulners(api_key=vulners_api_key)
        cve_data = vulners_api.searchExploit(cve)
        return [v['vhref'] for v in cve_data]
    
    else:
        print("VULNERS_API_KEY wasn't configured in the secrets!")
    
    return []

def get_cvss_data(cve_id):
    headers = {
        'accept': 'application/json',
        'accept-language': 'en-US,en;q=0.9',
        'authorization': 'Bearer vulncheck_651a1cb2fed5133603e938335ebeaf165dac1505beedeb51c8dbf2218b0d9fde',
        'cache-control': 'no-cache',
        'origin': 'https://vulncheck.com',
        'pragma': 'no-cache',
        'priority': 'u=1, i',
        'referer': 'https://vulncheck.com/',
        'sec-ch-ua': '"Google Chrome";v="125", "Chromium";v="125", "Not.A/Brand";v="24"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-site',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
    }

    params = {
        'cve': cve_id,
    }

    response = requests.get('https://api.vulncheck.com/v3/index/nist-nvd2', params=params, headers=headers)

    if response.status_code == 200:
        data = response.json()

        try:
            if data['data'][0]['metrics']['cvssMetricV31'][0]['cvssData']['vectorString'] :
                vector_string = data['data'][0]['metrics']['cvssMetricV31'][0]['cvssData']['vectorString']
                base_score = data['data'][0]['metrics']['cvssMetricV31'][0]['cvssData']['baseScore']
                base_severity = data['data'][0]['metrics']['cvssMetricV31'][0]['cvssData']['baseSeverity']
            elif data['data'][0]['metrics']['cvssMetricV30'][0]['cvssData']['vectorString'] :
                vector_string = data['data'][0]['metrics']['cvssMetricV30'][0]['cvssData']['vectorString']
                base_score = data['data'][0]['metrics']['cvssMetricV30'][0]['cvssData']['baseScore']
                base_severity = data['data'][0]['metrics']['cvssMetricV30'][0]['cvssData']['baseSeverity']
            else : 
                vector_string = ""
                base_score = ""
                base_severity = ""

            if data['data'][0]['weaknesses'][0]['description'][0]['value'] :
                cwe = data['data'][0]['weaknesses'][0]['description'][0]['value']
            else :
                cwe = ""

            print(cwe)
            return vector_string, base_score,base_severity,cwe
        except (KeyError, IndexError) as e:
            print("Error in extracting data:", e)
            return None, None,None,None
    else:
        return None, None,None,None

#################### GENERATE MESSAGES #########################

def generate_new_cve_message(cve_data: dict) -> str:
    ''' Generate new CVE message for sending to slack '''

    vendor = requests.get(f"https://services.nvd.nist.gov/rest/json/cves/2.0?cveId={cve_data['id']}")
    vector_string, base_score,base_severity,cwe = get_cvss_data(cve_data['id'])

    message = f"📝 [{cve_data['id']}](https://nvd.nist.gov/vuln/detail/{cve_data['id']}) 📝\n"
    keyword = cve_data.get('keyword', '').replace(" ", "\\_")

    if vector_string and base_score and base_severity:
        severity_icon = {
            'LOW': '🟡',
            'MEDIUM': '🟠',
            'HIGH': '🔴',
            'CRITICAL': '🟣'
        }.get(base_severity.upper(), '')
        message += f"{severity_icon}  *Base Severity*: #{base_severity}\n"
        message += f"🔮  *Base Score*: {base_score}\n"
        message += f"✨  *Vector String*: {vector_string}\n"

    print(cwe_data.get(cwe))
    print(cwe_data)
    print(cwe)
    if cwe :
        message += f"✨  *cwe*: {cwe} {cwe_data.get(cwe, "CWE ID not found")} \n"

    message += f"🏷️ *keyword*:  #{keyword}  \n"
    message += f"📅  *Published*: {cve_data['Published']}\n"
    message += "📓  *Summary*: " 
    cve_data["summary"] = cve_data["summary"].replace("_", "\\_")
    message += cve_data["summary"] if len(cve_data["summary"]) < 500 else cve_data["summary"][:500] + "..."
    
    if cve_data["vulnerable_configuration"]:
        message += f"\n🔓  *Vulnerable* (_limit to 10_): " + ", ".join(cve_data["vulnerable_configuration"][:10])
    
    message += "\n\n🟢 ℹ️  *More information*: \n" + "\n".join(cve_data["references"][:5])
    
    message += "\n"

    #message += "\n\n(Check the bots description for more information about the bot)\n"
    
    return message


def generate_modified_cve_message(cve_data: dict) -> str:
    ''' Generate modified CVE message for sending to slack '''

    message = f"📣 [{cve_data['id']}](https://nvd.nist.gov/vuln/detail/{cve_data['id']})\\(_{cve_data['cvss']}_\\) was modified the {cve_data['last-modified'].split('T')[0]} \\(_originally published the {cve_data['Published'].split('T')[0]}_\\)\n"
    return message


def generate_public_expls_message(public_expls: list) -> str:
    ''' Given the list of public exploits, generate the message '''

    message = ""

    if public_expls:
        message = "😈  *Public Exploits* (_limit 20_)  😈\n" + "\n".join(public_expls[:20])

    return message


#################### SEND MESSAGES #########################

def send_slack_mesage(message: str, public_expls_msg: str):
    ''' Send a message to the slack group '''

    slack_url = os.getenv('SLACK_WEBHOOK')

    if not slack_url:
        print("SLACK_WEBHOOK wasn't configured in the secrets!")
        return
    
    json_params = {
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn", 
                    "text": message
                }
            },
            {
                "type": "divider"
            }
        ]
    }

    if public_expls_msg:
        json_params["blocks"].append({
                "type": "section",
                "text": {
                    "type": "mrkdwn", 
                    "text": public_expls_msg
                }
        })

    requests.post(slack_url, json=json_params)


def send_telegram_message(message: str, public_expls_msg: str):
    ''' Send a message to the telegram group '''

    telegram_bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    telegram_chat_id = os.getenv('TELEGRAM_CHAT_ID')    
    telegram_thread_id = os.getenv('TELEGRAM_THREAD_ID') 

    if not telegram_bot_token:
        print("TELEGRAM_BOT_TOKEN wasn't configured in the secrets!")
        return
    
    if not telegram_chat_id:
        print("TELEGRAM_CHAT_ID wasn't configured in the secrets!")
        return
    
    if not telegram_thread_id:
        print("TELEGRAM_THREAD_ID wasn't configured in the secrets!")
        return
    
    if public_expls_msg:
        message = message + "\n" + public_expls_msg

    message = message.replace(".", "\\.").replace("-", "\\-").replace("{","\\{").replace("}","\\}").replace("=","\\=").replace("#","\\#")
    r = requests.get(f'https://api.telegram.org/bot{telegram_bot_token}/sendMessage?parse_mode=MarkdownV2&text={urllib.parse.quote_plus(message)}&chat_id={telegram_chat_id}&message_thread_id={telegram_thread_id}')

    resp = r.json()
    if not resp['ok']:
        print("ERROR SENDING TO TELEGRAM: "+ message.split("\n")[0] + resp["description"])

            
def send_discord_message(message: str, public_expls_msg: str):
    ''' Send a message to the discord channel webhook '''

    discord_webhok_url = os.getenv('DISCORD_WEBHOOK_URL')

    if not discord_webhok_url:
        print("DISCORD_WEBHOOK_URL wasn't configured in the secrets!")
        return
    
    if public_expls_msg:
        message = message + "\n" + public_expls_msg

    message = message.replace("(", "\\(").replace(")", "\\)").replace("_", "").replace("[","\\[").replace("]","\\]").replace("{","\\{").replace("}","\\}").replace("=","\\=")
    webhook = Webhook.from_url(discord_webhok_url, adapter=RequestsWebhookAdapter())
    if public_expls_msg:
        message = message + "\n" + public_expls_msg
    
    webhook.send(message)

def send_pushover_message(message: str, public_expls_msg: str):
    ''' Send a message to the pushover device '''

    pushover_device_name = os.getenv('PUSHOVER_DEVICE_NAME')
    pushover_user_key = os.getenv('PUSHOVER_USER_KEY')
    pushover_token = os.getenv('PUSHOVER_TOKEN') 

    if not pushover_device_name:
        print("PUSHOVER_DEVICE_NAME wasn't configured in the secrets!")
        return 
    if not pushover_user_key:
        print("PUSHOVER_USER_KEY wasn't configured in the secrets!")
        return
    if not pushover_token:
        print("PUSHOVER_TOKEN wasn't configured in the secrets!")
        return
    if public_expls_msg:
        message = message + "\n" + public_expls_msg

    data = { "token": pushover_token, "user": pushover_user_key, "message": message , "device": pushover_device_name}
    try:
        r = requests.post("https://api.pushover.net/1/messages.json", data = data)
    except Exception as e:
        print("ERROR SENDING TO PUSHOVER: "+ message.split("\n")[0] +message)
#################### MAIN #########################

def main():
    #Load configured keywords
    load_keywords()

    #Start loading time of last checked ones
    load_lasttimes()

    #Find a publish new CVEs
    new_cves = get_new_cves()
    
    new_cves_ids = [ncve['id'] for ncve in new_cves]
    print(f"New CVEs discovered: {new_cves_ids}")
    
    for new_cve in new_cves:
        public_exploits = search_exploits(new_cve['id'])
        cve_message = generate_new_cve_message(new_cve)
        public_expls_msg = generate_public_expls_message(public_exploits)
        send_slack_mesage(cve_message, public_expls_msg)
        send_telegram_message(cve_message, public_expls_msg)
        send_discord_message(cve_message, public_expls_msg)
        send_pushover_message(cve_message, public_expls_msg)
    
    #Find and publish modified CVEs
    modified_cves = get_modified_cves()

    modified_cves = [mcve for mcve in modified_cves if not mcve['id'] in new_cves_ids]
    modified_cves_ids = [mcve['id'] for mcve in modified_cves]
    print(f"Modified CVEs discovered: {modified_cves_ids}")
    
    for modified_cve in modified_cves:
        public_exploits = search_exploits(modified_cve['id'])
        cve_message = generate_modified_cve_message(modified_cve)
        public_expls_msg = generate_public_expls_message(public_exploits)
        send_slack_mesage(cve_message, public_expls_msg)
        send_telegram_message(cve_message, public_expls_msg)
        send_pushover_message(cve_message, public_expls_msg)

    #Update last times
    update_lasttimes()


if __name__ == "__main__":
    main()
