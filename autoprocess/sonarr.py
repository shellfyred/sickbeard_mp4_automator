import sys
import os
import logging
import json
import time


def processEpisode(dirName, settings, nzbGet=False, logger=None):

    if nzbGet:
        errorprefix = "[ERROR] "
        infoprefix = "[INFO] "
    else:
        errorprefix = ""
        infoprefix = ""

    # Setup logging
    if logger:
        log = logger
    else:
        log = logging.getLogger(__name__)

    log.info("%sSonarr notifier started." % infoprefix)

    # Import Requests
    try:
        import requests
    except ImportError:
        log.exception("%sPython module REQUESTS is required. Install with 'pip install requests' then try again." % errorprefix)
        log.error("%sPython executable path is %s" % (errorprefix, sys.executable))
        return False

    host = settings.Sonarr['host']
    port = settings.Sonarr['port']
    apikey = settings.Sonarr['apikey']

    if apikey == '':
        log.error("%sYour Sonarr API Key can not be blank. Update autoProcess.ini." % errorprefix)
        return False

    try:
        ssl = int(settings.Sonarr['ssl'])
    except:
        ssl = 0
    if ssl:
        protocol = "https://"
    else:
        protocol = "http://"

    webroot = settings.Sonarr['web_root']
    url = protocol + host + ":" + port + webroot + "/api/command"
    payload = {'name': 'downloadedepisodesscan', 'path': dirName}
    headers = {'X-Api-Key': apikey}

    log.debug("Sonarr host: %s." % host)
    log.debug("Sonarr port: %s." % port)
    log.debug("Sonarr webroot: %s." % webroot)
    log.debug("Sonarr apikey: %s." % apikey)
    log.debug("Sonarr protocol: %s." % protocol)
    log.debug("URL '%s' with payload '%s.'" % (url, payload))

    log.info("%sRequesting Sonarr to scan directory '%s'." % (infoprefix, dirName))

    try:
        r = requests.post(url, data=json.dumps(payload), headers=headers)
        rstate = r.json()
        log.info("%sSonarr response: %s." % (infoprefix, rstate['state']))
         # wait for radarr to finish processing before we try to delete the folder
        update_url = url + "/" + str(rstate['id'])
        update_request = requests.get(update_url, headers=headers)
        update_state = update_request.json()
        while str(update_state['state']) != "completed":
            log.info("Sleeping while Sonarr processes new file")
            time.sleep(60)
            update_request = requests.get(update_url, headers=headers)
            update_state = update_request.json()
        log.info("Sonarr status changed to %s" % update_state['state'])
        return True
    except:
        log.exception("%sUpdate to Sonarr failed, check if Sonarr is running, autoProcess.ini settings and make sure your Sonarr settings are correct (apikey?), or check install of python modules requests." % errorprefix)
        return False
