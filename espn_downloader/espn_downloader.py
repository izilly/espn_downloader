#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
#  Copyright (c) 2013 Will Adams
#  Distributed under the terms of the Modified BSD License.
#  The full license is in the file LICENSE, distributed with this software.

from datetime import datetime, timedelta
from lxml import etree
import os.path
from collections import OrderedDict
import random
import urllib.request
import subprocess
import re
from iz_dvd.user_input import prompt_user_list


USER_INFO_FILE = os.path.expanduser('~/.config/iz_espn/userdata.xml')
ESPN_CONFIG_URL = 'http://espn.go.com/watchespn/player/config'
AUTH_URL_BASE = ('https://espn-ws.bamnetworks.com/'
                 'pubajaxws/bamrest/MediaService2_0/'
                 'op-findUserVerifiedEvent/v-2.1')
NETWORK_IDS = {'n360': 'espn3',
               'n501': 'espn1',
               'n502': 'espn2',
               'n599': 'espnu',
               'goalline': 'goalline',
               'buzzerbeater': 'buzzerbeater'}
DOWNLOAD_DIR = os.path.expanduser('~/Videos/espn')


def get_replay_url(days=3, channels=['espn3']):
    channels = ','.join(channels)
    curdate = datetime.utcnow()
    enddate = curdate.strftime("%Y%m%d")
    startdate = (curdate-timedelta(days)).strftime("%Y%m%d")
    events_url_base = 'http://espn.go.com/watchespn/feeds/startup?action=replay'
    events_url = '{}&channel={}&endDate={}&startDate={}'.format(events_url_base,
                                                                channels,
                                                                enddate,
                                                                startdate)
    return events_url

def get_events(url, sport=None):
    xml = etree.parse(url)
    root = xml.getroot()
    if sport:
        events = root.xpath('event[sport[text() = $sport]]', sport=sport)
    else:
        events = list(root)
    return events

def prompt_events(events):
    event_infos = [get_event_info(i) for i in events]
    choices = ['{} {:^12} {:6} {}'.format(i['channel'],
                                          i['sport'],
                                          '{:%-m/%-d}'.format(i['start_time']),
                                          i['name']) for i in event_infos]
    #~ choices = ['{} {:^12} {}'.format(NETWORK_IDS[i.find('networkId').text], 
                                     #~ i.find('sportDisplayValue').text, 
                                     #~ i.find('name').text) 
               #~ for i in events]
    response = prompt_user_list(choices)
    chosen = events[response]
    return chosen

def get_user_info():
    xml = etree.parse(USER_INFO_FILE)
    root = xml.getroot()
    affiliate_name = root.find('affiliate/name').text
    swid = root.find('personalization').get('swid')
    identityPointId = ':'.join([affiliate_name, swid])
    return {'identityPointId': identityPointId}

def get_network_info(channel='espn3'):
    xml = etree.parse(ESPN_CONFIG_URL)
    root = xml.getroot()
    network = root.xpath('.//network[@name=$channel]', channel=channel)[0]
    playerId = network.get('playerId')
    cdnName = network.get('defaultCdn')
    channel = network.get('name')
    network_info = {'playerId': playerId, 'cdnName': cdnName, 
                    'channel': channel}
    #~ return playerId, cdnName, channel
    return network_info

def get_event_info(event, file_ext='mp4'):
    eventid = event.get('id')
    bamContentId = event.get('bamContentId')
    bamEventId = event.get('bamEventId')
    name = event.find('name').text
    sport = event.find('sportDisplayValue').text
    start_timestamp = int(event.find('startTimeGmtMs').text) / 1000
    start_time = datetime.fromtimestamp(start_timestamp)
    channel = NETWORK_IDS[event.find('networkId').text]
    filename = sanitize_filename('{}-{}-{}.{}'.format(sport, name, 
                                                start_time.strftime('%Y.%m.%d'),
                                                file_ext))
    event = {'eventid': eventid, 'bamContentId': bamContentId, 
             'bamEventId':bamEventId, 'name': name, 'sport': sport,
             'filename': filename, 'start_time': start_time, 'channel': channel}
    return event

def sanitize_filename(name, space_char='.'):
    #~ linux_invalid = [r'/']
    #~ windows_invalid = [r'<', r'>', r':', r'"', r'/', r'\', r'|', r'?', r'*']
    filename = name
    filename = re.sub(r' ', space_char, filename).strip(space_char)
    filename = re.sub(r'[:/\<>|*?]', ';', filename).strip(';')
    #~ filename = re.sub(r'"', "'", filename)
    filename = re.sub('["\']', "", filename)
    return filename

def get_auth_url(event):
    event_info = get_event_info(event)
    networkId = event.find('networkId').text
    channel = NETWORK_IDS[networkId]
    network_info = get_network_info(channel)
    user_info = get_user_info()
    auth_params = OrderedDict()
    auth_params['playbackScenario'] = 'FMS_CLOUD'
    auth_params['channel'] = channel
    auth_params['partnerContentId'] = event_info['eventid']
    auth_params['eventId'] = event_info['bamEventId']
    auth_params['contentId'] = event_info['bamContentId']
    auth_params['rand'] = '{:.16f}'.format(random.random())
    auth_params['cdnName'] = network_info['cdnName']
    auth_params['identityPointId'] = user_info['identityPointId']
    auth_params['playerId'] = network_info['playerId']
    auth_params_str = '&'.join(['='.join([k,v]) for k,v in auth_params.items()])
    auth_url = '{}?{}'.format(AUTH_URL_BASE, auth_params_str)
    return auth_url

def get_smil_url(auth_url):
    xml = etree.parse(urllib.request.urlopen(auth_url))
    root = xml.getroot()
    smil_url = root.find('{*}user-verified-event/'
                    '{*}user-verified-content/'
                    '{*}user-verified-media-item/'
                    '{*}url').text
    return smil_url

def get_rtmp_info(smil_url, quality=None):
    rtmp_auth = smil_url.partition('?')[2]
    xml = etree.parse(urllib.request.urlopen('{}&{:.16f}'.format(smil_url,
                                                             random.random())))
    root = xml.getroot()
    video_streams = root.findall('body/switch/video')
    video_bitrates = [int(i.get('system-bitrate')) for i in video_streams]
    if quality is None:
        quality = video_bitrates[-1]
    else:
        quality = video_bitrates[quality]
    stream = video_streams[video_bitrates.index(quality)]
    playpath = stream.get('src')
    rtmp_url_base = root.find('head/meta').get('base')
    rtmp_url = '{}/?{}'.format(rtmp_url_base, rtmp_auth)
    rtmp_info = {'rtmp_url': rtmp_url, 'playpath': playpath}
    return rtmp_info

def download_stream(rtmp_info, path):
    args = ['rtmpdump', '-r', rtmp_info['rtmp_url'],
            '-y', rtmp_info['playpath'], '-m', '360',
            '-e', '-o', path]
    ret_code = 1
    while ret_code != 0:
        ret_code = subprocess.call(args)
    return path

def get_event(event):
    event_info = get_event_info(event)
    download_path = os.path.join(DOWNLOAD_DIR, event_info['filename'])
    auth_url = get_auth_url(event)
    smil_url = get_smil_url(auth_url)
    rtmp_info = get_rtmp_info(smil_url)
    downloaded = download_stream(rtmp_info, download_path)
    return downloaded

def main():
    events = get_events(get_replay_url(7), sport='FOOTBALL')
    chosen = prompt_events(events)
    downloaded = get_event(chosen)
    
    return 0

if __name__ == '__main__':
    main()

