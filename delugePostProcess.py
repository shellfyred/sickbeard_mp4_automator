#!/usr/bin/env python

import os
import sys
import rarfile
import time
from autoprocess import autoProcessTV, autoProcessMovie, autoProcessTVSR, sonarr, radarr
from readSettings import ReadSettings
from mkvtomp4 import MkvtoMp4
from deluge_client import DelugeRPCClient
import logging
from logging.config import fileConfig

def extractRar(rar_path, rar_filename):
    """
        expects path and filename to .rar file
        extracts to same dir as rar file and returns
        extracted file
    """
    files = []
    filepath = os.path.join(rar_path, rar_filename)
    original_filename = os.path.basename(rar_filename)
    destination = os.path.dirname(filepath)
    with rarfile.RarFile(filepath) as opened_rar:
        for f in opened_rar.infolist():
            files.append(rar_filename.replace(original_filename, str(f.filename)))
        opened_rar.extractall(destination)
    return files

fileConfig(os.path.join(os.path.dirname(sys.argv[0]), 'logging.ini'), defaults={'logfilename': os.path.join(os.path.dirname(sys.argv[0]), 'info.log').replace("\\", "/")})
log = logging.getLogger("delugePostProcess")
pid = str(os.getpid())
pidfile = '/tmp/locktest.pid'

while os.path.isfile(pidfile):
    logging.debug("%s exists sleeping" % pidfile)
    time.sleep(randint(60,90))
logging.debug("creating pidfile for %s" % pid)
file(pidfile, 'w').write(pid)

try:

    log.info("Deluge post processing started.")

    settings = ReadSettings(os.path.dirname(sys.argv[0]), "autoProcess.ini")
    categories = [settings.deluge['sb'], settings.deluge['cp'], settings.deluge['sonarr'], settings.deluge['radarr'], settings.deluge['sr'], settings.deluge['bypass']]
    remove = settings.deluge['remove']

    if len(sys.argv) < 4:
        log.error("Not enough command line parameters present, are you launching this from deluge?")
        sys.exit()

    path = str(sys.argv[3])
    torrent_name = str(sys.argv[2])
    torrent_id = str(sys.argv[1])
    delete_dir = None

    log.debug("Path: %s." % path)
    log.debug("Torrent: %s." % torrent_name)
    log.debug("Hash: %s." % torrent_id)

    client = DelugeRPCClient(host=settings.deluge['host'], port=int(settings.deluge['port']), username=settings.deluge['user'], password=settings.deluge['pass'])
    client.connect()

    if client.connected:
        log.info("Successfully connected to Deluge")
    else:
        log.error("Failed to connect to Deluge")
        sys.exit()

    torrent_data = client.call('core.get_torrent_status', torrent_id, ['files', 'label'])
    torrent_files = torrent_data['files']
    category = torrent_data['label'].lower()

    settings.delete = False
    files = []
    log.debug("List of files in torrent:")
    for contents in torrent_files:
        files.append(contents['path'])
        if os.path.splitext(contents['path'])[1][1:] == 'rar':
            log.debug("rar found:  %s, extracting" % contents['path'])
            files = files + extractRar(path, contents['path'])
            settings.delete = True
        log.debug(contents['path'])

    if category.lower() not in categories:
        log.error("No valid category detected.")
        sys.exit()

    if len(categories) != len(set(categories)):
        log.error("Duplicate category detected. Category names must be unique.")
        sys.exit()

    if settings.deluge['convert']:
        # Check for custom Deluge output_dir
        if settings.deluge['output_dir']:
            settings.output_dir = settings.deluge['output_dir']
            log.debug("Overriding output_dir to %s." % settings.deluge['output_dir'])

        # Perform conversion.
        if not settings.output_dir:
            suffix = "-convert"
            torrent_name = torrent_name[:260-len(suffix)]
            settings.output_dir = os.path.join(path, ("%s%s" % (torrent_name, suffix)))
            if not os.path.exists(settings.output_dir):
                os.mkdir(settings.output_dir)
            delete_dir = settings.output_dir

        converter = MkvtoMp4(settings)

        for filename in files:
            inputfile = os.path.join(path, filename)
            if MkvtoMp4(settings).validSource(inputfile):
                log.info("Converting file %s at location %s." % (inputfile, settings.output_dir))
                try:
                    output = converter.process(inputfile)
                except:
                    log.exception("Error converting file %s." % inputfile)

        path = converter.output_dir
    else:
        suffix = "-copy"
        torrent_name = torrent_name[:260-len(suffix)]
        newpath = os.path.join(path, ("%s%s" % (torrent_name, suffix)))
        if not os.path.exists(newpath):
            os.mkdir(newpath)
        for filename in files:
            inputfile = os.path.join(path, filename)
            log.info("Copying file %s to %s." % (inputfile, newpath))
            shutil.copy(inputfile, newpath)
        path = newpath
        delete_dir = newpath

    # Send to Sickbeard
    if (category == categories[0]):
        log.info("Passing %s directory to Sickbeard." % path)
        autoProcessTV.processEpisode(path, settings)
    # Send to CouchPotato
    elif (category == categories[1]):
        log.info("Passing %s directory to Couch Potato." % path)
        autoProcessMovie.process(path, settings, torrent_name)
    # Send to Sonarr
    elif (category == categories[2]):
        log.info("Passing %s directory to Sonarr." % path)
        sonarr.processEpisode(path, settings)
    elif (category == categories[3]):
        log.info("Passing %s directory to Radarr." % path)
        radarr.processMovie(path, settings)
    elif (category == categories[4]):
        log.info("Passing %s directory to Sickrage." % path)
        autoProcessTVSR.processEpisode(path, settings)
    elif (category == categories[5]):
        log.info("Bypassing any further processing as per category.")

    if delete_dir:
        if os.path.exists(delete_dir):
            try:
                os.rmdir(delete_dir)
                log.debug("Successfully removed tempoary directory %s." % delete_dir)
            except:
                log.exception("Unable to delete temporary directory.")

    if remove:
        try:
            client.call('core.remove_torrent', torrent_id, True)
        except:
            log.exception("Unable to remove torrent from deluge.")
except:
    logging.debug("removing pidfile")
    os.unlink(pidfile)
    pass