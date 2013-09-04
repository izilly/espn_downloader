#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
#  Copyright (c) 2013 Will Adams
#  Distributed under the terms of the Modified BSD License.
#  The full license is in the file LICENSE, distributed with this software.

import argparse
import sys
from datetime import datetime, timedelta
import time
from lxml import etree
import os
import os.path
from collections import OrderedDict
import random
import urllib.request
import subprocess
import re
from iz_dvd.user_input import prompt_user_list

# User config ----------------------------------------------------------------
#~ DOWNLOAD_DIR = os.path.expanduser('~/Videos/espn')
#~ DATA_DIR = os.path.expanduser('~/.config/iz_espn')
#~ FORCE_REFRESH_MINUTES = 60
#~ USER_INFO_FILE = os.path.expanduser('~/.config/iz_espn/userdata.xml')
# ESPN config ----------------------------------------------------------------
ESPN_CONFIG_URL = 'http://espn.go.com/watchespn/player/config'
FEEDS_URL_BASE = 'http://espn.go.com/watchespn/feeds/startup?action=replay'
LIVE_URL_BASE = 'http://espn.go.com/watchespn/feeds/startup?action=live'
AUTH_URL_BASE = ('https://espn-ws.bamnetworks.com/'
                 'pubajaxws/bamrest/MediaService2_0/'
                 'op-findUserVerifiedEvent/v-2.1')
NETWORK_IDS = {'n360': 'espn3',
               'n501': 'espn1',
               'n502': 'espn2',
               'n599': 'espnu',
               'goalline': 'goalline',
               'buzzerbeater': 'buzzerbeater'}
#-----------------------------------------------------------------------------

def get_options():
    parser = argparse.ArgumentParser(prog='iz_espn')
    parser.add_argument('-m', '--mode', default='replay', 
                        choices=['replay', 'live'])
    parser.add_argument('-d', '--days', default='3', type=int)
    parser.add_argument('-b', '--bitrate', choices=['max', 'min', 'prompt',
                                                    '400k', '800k', '1200k', 
                                                    '2200k'],
                        default='max')
    parser.add_argument('-l', '--list-sports', action='store_true')
    parser.add_argument('-s', '--search', action='append')
    parser.add_argument('--search-sports', action='append')
    parser.add_argument('--download-dir', default=None, help='Default: current directory')
    parser.add_argument('--cache-dir', default='~/.config/iz_espn', help='Directory for retrieving userdata.xml and storing events cache.')
    parser.add_argument('--userdata-xml', default=None, help='Default: <cache-dir>/userdata.xml')
    parser.add_argument('-r', '--force-refresh-minutes', type=int, default=60)
    options = parser.parse_args()
    if options.download_dir is None:
        options.download_dir = os.getcwd()
    else:
        options.download_dir = os.path.expandvars(options.download_dir)
        options.download_dir = os.path.expanduser(options.download_dir)
    options.cache_dir = os.path.expandvars(options.cache_dir)
    options.cache_dir = os.path.expanduser(options.cache_dir)
    if options.userdata_xml is None:
        options.userdata_xml = os.path.join(options.cache_dir, 'userdata.xml')
    else:
        options.userdata_xml = os.path.expandvars(options.userdata_xml)
        options.userdata_xml = os.path.expanduser(options.userdata_xml)

    return options

OPTIONS = get_options()

#-----------------------------------------------------------------------------

def get_feeds_url(start, end=None, channels=['espn3']):
    channels = ','.join(channels)
    start_date = start.strftime('%Y%m%d')
    #~ end_date = end.strftime('%Y%m%d')
    feeds_url = '{}&channel={}&startDate={}'.format(FEEDS_URL_BASE,
                                                                channels,
                                                                start_date)
    if end:
        feeds_url = '{}&{}'.format(feeds_url, end.strftime('%Y%m%d'))
    print('{1}\nFeeds URL: {0}\n{1}\n'.format(feeds_url, '='*78))
    return feeds_url

def get_live_url(channels=['espn3']):
    channels = ','.join(channels)
    #~ start_date = start.strftime('%Y%m%d')
    #~ end_date = end.strftime('%Y%m%d')
    live_url = '{}&channel={}'.format(LIVE_URL_BASE,
                                                                channels)
    print('{1}\nLive URL: {0}\n{1}\n'.format(live_url, '='*78))
    return live_url

def get_events(days=7, force_refresh_minutes=None, channels=['espn3'], 
               mode='replay'):
    if mode == 'live':
        live_url = get_live_url()
        events = parse_feed(live_url)
        return events
    #
    if force_refresh_minutes is None:
        force_refresh_minutes = OPTIONS.force_refresh_minutes
    events = []
    now = datetime.now()
    end = now + timedelta(days=1)
    start = now-timedelta(days)
    for c in channels:
        channel_events = []
        cached_url = os.path.join(OPTIONS.cache_dir, '{}.xml'.format(c))
        new_url = None
        if os.path.exists(cached_url):
            cached_xml = etree.parse(cached_url)
            cached_feed = cached_xml.getroot()
            channel_events.extend(parse_feed(cached_feed))
            cache_updated = cached_feed.get('updated')
            if cache_updated:
                cache_updated = datetime.fromtimestamp(float(cache_updated))
            else:
                cache_updated = channel_events[0]['start_time']
            # test if oldest cached event is less than <days> ago
            if channel_events[-1]['start_time'] > start:
                #~ cache_updated = now
                new_url = get_feeds_url(start, [c])
            # test if cache has been updated within last 30 minutes
            elif cache_updated < now - timedelta(minutes=force_refresh_minutes):
                new_url = get_feeds_url(cache_updated, [c])
        else:
            new_url = get_feeds_url(start, [c])
        if new_url:
            print('Fetching new events from server...')
            new_events = parse_feed(new_url)
            new_events = [n for n in parse_feed(new_url) if n['eventid']
                          not in [i['eventid'] for i in channel_events]]
            channel_events = new_events + channel_events
            update_cache(cached_url, channel_events, now)
        else:
            print('Cached events less than {} minutes old. '
                  'Using cached events only...'.format(force_refresh_minutes))
        events.extend(channel_events)
    events = sorted(events, key=lambda e: e['start_time'], reverse=True)
    events = filter_events(events)
    return events

def update_cache(path, events, updated, days=90):
    # TODO: save some number of old cache files?
    updated = str(updated.timestamp())
    old = datetime.utcnow() - timedelta(days=days)
    keep_events = [i['xml'] for i in events if i['start_time'] > old]

    root = etree.Element('events', updated=updated)
    root.extend(keep_events)
    tree = etree.ElementTree(root)
    tree.write(path, encoding='UTF-8', pretty_print=True)

def parse_feed(feed):
    if type(feed) == etree._Element:
        root = feed
    else:
        xml = etree.parse(feed)
        root = xml.getroot()
    events = [get_event_info(i) for i in root]
    events = sorted(events, key=lambda e: e['start_time'], reverse=True)
    return events

def filter_events(events):
    events = filter_by_time(events)
    if OPTIONS.list_sports:
        events = prompt_sports(events)
    if OPTIONS.search:
        events = search_events(events, OPTIONS.search)
    return events

def search_events(events, regex):
    filtered = []
    for pat in regex:
        found = [i for i in events 
                 if re.search(pat, i['xml'].xpath('string()'), re.I)]
        filtered.extend(found)
    return filtered

def filter_by_time(events, days=None):
    if not days:
        days = OPTIONS.days
    now = datetime.now()
    old = now - timedelta(days=days)
    filtered = [i for i in events if i['start_time'] >= old ]
    return filtered

def filter_by_sport(events, sports):
    if type(sports) is not list:
        sports = [sports]
    filtered = []
    for s in sports:
        found = [i for i in events if i['sport'].lower() == s.lower()]
        filtered.extend(found)
    return filtered

def prompt_user(choices, header=None):
    if not choices:
        print('No events to display with current options. Exiting...')
        sys.exit()
    response = prompt_user_list(choices, header=header)
    if response is False:
        print('Exiting...')
        sys.exit()
    else:
        return response

def prompt_events(events):
    #~ if not events:
        #~ print('No events to display with current options. Exiting...')
        #~ sys.exit()
    choices = ['{} {:^12} {:6} {}'.format(i['channel'],
                                          i['sport'],
                                          '{:%-m/%-d}'.format(i['start_time']),
                                          i['name']) for i in events]
    #~ response = prompt_user_list(choices)
    response = prompt_user(choices, header='Available Events')
    #~ if response is False:
        #~ print('Exiting...')
        #~ sys.exit()
    chosen = events[response]
    return chosen

def prompt_sports(events):
    sports = sorted(list(set([i['sport'] for i in events])))
    sports[:0] = ['All Sports']
    response = prompt_user(sports, header='Sports')
    if response == 0:
        return events
    chosen = sports[response]
    filtered = filter_by_sport(events, chosen)
    return filtered

def get_user_info():
    xml = etree.parse(OPTIONS.userdata_xml)
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
    print('{1}\nNetwork Info: {0}\n{1}\n'.format(network_info, '='*78), sep='\n')
    return network_info

def get_event_info(event, file_ext='mp4'):
    eventid = event.get('id')
    bamContentId = event.get('bamContentId')
    bamEventId = event.get('bamEventId')
    name = event.find('name').text
    sport = event.find('sportDisplayValue').text
    start_timestamp = int(event.find('startTimeGmtMs').text) / 1000
    start_time = datetime.fromtimestamp(start_timestamp)
    networkId = event.find('networkId').text
    channel = NETWORK_IDS[networkId]
    filename = sanitize_filename('{}-{}-{}.{}'.format(sport, name, 
                                                start_time.strftime('%Y.%m.%d'),
                                                file_ext))
    event = {'eventid': eventid, 'bamContentId': bamContentId, 
             'bamEventId':bamEventId, 
             'name': name, 'sport': sport, 'start_time': start_time, 
             'channel': channel, 'networkId': networkId,
             'filename': filename, 'xml': event}
    return event

def sanitize_filename(name, space_char='.'):
    #~ linux_invalid = [r'/']
    #~ windows_invalid = [r'<', r'>', r':', r'"', r'/', r'\', r'|', r'?', r'*']
    filename = name
    filename = re.sub(r' ', space_char, filename).strip(space_char)
    filename = re.sub(r'[:/\<>|*?]', ';', filename).strip(';')
    filename = re.sub('["\']', "", filename)
    return filename

def get_auth_url(event):
    #~ event_info = get_event_info(event)
    #~ networkId = event.find('networkId').text
    networkId = event['networkId']
    #~ channel = NETWORK_IDS[networkId]
    channel = event['channel']
    network_info = get_network_info(channel)
    user_info = get_user_info()
    auth_params = OrderedDict()
    auth_params['playbackScenario'] = 'FMS_CLOUD'
    auth_params['channel'] = channel
    auth_params['partnerContentId'] = event['eventid']
    auth_params['eventId'] = event['bamEventId']
    auth_params['contentId'] = event['bamContentId']
    auth_params['rand'] = '{:.16f}'.format(random.random())
    auth_params['cdnName'] = network_info['cdnName']
    auth_params['identityPointId'] = user_info['identityPointId']
    auth_params['playerId'] = network_info['playerId']
    auth_params_str = '&'.join(['='.join([k,v]) for k,v in auth_params.items()])
    auth_url = '{}?{}'.format(AUTH_URL_BASE, auth_params_str)
    print('{1}\nAuth URL: {0}\n{1}\n'.format(auth_url, '='*78), sep='\n')
    return auth_url

def get_smil_url(auth_url):
    xml = etree.parse(urllib.request.urlopen(auth_url))
    root = xml.getroot()
    smil_url = root.find('{*}user-verified-event/'
                    '{*}user-verified-content/'
                    '{*}user-verified-media-item/'
                    '{*}url').text
    print('{1}\nSMIL URL: {0}\n{1}\n'.format(smil_url, '='*78), sep='\n')
    return smil_url

def get_rtmp_info(smil_url, quality=None):
    rtmp_auth = smil_url.partition('?')[2]
    xml = etree.parse(urllib.request.urlopen('{}&{:.16f}'.format(smil_url,
                                                             random.random())))
    root = xml.getroot()
    video_streams = root.findall('body/switch/video')
    #~ video_bitrates = [int(i.get('system-bitrate')) for i in video_streams]
    #~ if quality == 'prompt':
        #~ choices = ['{}k'.format(i/1000) for i in video_bitrates]
        #~ response = prompt_user(choices, header='Available Bitrates')
        #~ quality = video_bitrates[response]
    #~ if quality in ['max', None]:
        #~ quality = max(video_bitrates)
    #~ elif quality == 'min':
        #~ quality = min(video_bitrates)
    #~ else:
        #~ if type(quality) == int:
            #~ bitrate = quality
        #~ else:
            #~ bitrate = int(quality.strip('k')) * 1000
        #~ diffs = [i - bitrate for i in video_bitrates]
        #~ abs_diffs = [abs(i) for i in diffs]
        #~ closest = min(abs_diffs)
        #~ if closest in diffs:
            #~ quality = video_bitrates[diffs.index(closest)]
        #~ else:
            #~ quality = video_bitrates[abs_diffs.index(closest)]
    #~ stream = video_streams[video_bitrates.index(quality)]
    stream = video_streams[quality]
    print(etree.tostring(stream, pretty_print=True).decode())
    playpath = stream.get('src')
    rtmp_url_base = root.find('head/meta').get('base')
    #~ rtmp_url = '{}/?{}'.format(rtmp_url_base, rtmp_auth)
    rtmp_info = {'rtmp_url': rtmp_url_base, 'playpath': playpath, 
                 'rtmp_auth': rtmp_auth}
    print('{1}\nRTMP Info: {0}\n{1}\n'.format(rtmp_info, '='*78), sep='\n')
    return rtmp_info

def select_bitrate(quality):
    video_bitrates = [400000, 800000, 1200000, 2200000]
    if quality == 'prompt':
        choices = ['{}k'.format(i/1000) for i in video_bitrates]
        response = prompt_user(choices, header='Available Bitrates')
        quality = video_bitrates[response]
    if quality in ['max', None]:
        quality = max(video_bitrates)
    elif quality == 'min':
        quality = min(video_bitrates)
    else:
        if type(quality) == int:
            bitrate = quality
        else:
            bitrate = int(quality.strip('k')) * 1000
        diffs = [i - bitrate for i in video_bitrates]
        abs_diffs = [abs(i) for i in diffs]
        closest = min(abs_diffs)
        if closest in diffs:
            quality = video_bitrates[diffs.index(closest)]
        else:
            quality = video_bitrates[abs_diffs.index(closest)]
    bitrate = video_bitrates.index(quality)
    print('{1}\nBitrate: {0:.0f}k\n{1}\n'.format(video_bitrates[bitrate]/1000, '='*78), sep='\n')
    return bitrate
    

def download_stream(rtmp_info, path, mode='replay'):
    if mode == 'replay':
        url = '{}/?{}'.format(rtmp_info['rtmp_url'], rtmp_info['rtmp_auth'])
        playpath = rtmp_info['playpath']
    else:
        url = rtmp_info['rtmp_url']
        playpath = '{}?{}'.format(rtmp_info['playpath'], rtmp_info['rtmp_auth'])
    args = ['rtmpdump', '-r', url,
            '-y', playpath, '-m', '360']
            #~ '-e', '-o', path]
    if mode == 'replay':
        args.extend(['-e', '-o', path])
    else:
        args.extend(['-v', '-Y', '-o', path])

    print('{1}\nRTMP cmd: {0}\n{1}\n'.format(' '.join(args), '='*78), sep='\n')
    ret_code = 1
    tries = 0
    while ret_code != 0 and tries <= 100:
        ret_code = subprocess.call(args)
        tries += 1
        time.sleep(.2)
    return path

def get_event(event, quality=None, mode='replay'):
    #~ event_info = get_event_info(event)
    download_path = os.path.join(OPTIONS.download_dir, event['filename'])
    auth_url = get_auth_url(event)
    smil_url = get_smil_url(auth_url)
    quality = select_bitrate(OPTIONS.bitrate)
    rtmp_info = get_rtmp_info(smil_url, quality=quality)
    downloaded = download_stream(rtmp_info, download_path, mode=mode)
    return downloaded

def main(mode='replay'):
    events = get_events(OPTIONS.days, mode=OPTIONS.mode)
    chosen = prompt_events(events)
    print('{1}\nEvent Info: {0}\n{1}\n'.format(chosen, '='*78), sep='\n')
    #~ quality = select_bitrate(OPTIONS.bitrate)
    downloaded = get_event(chosen, quality=OPTIONS.bitrate, mode=OPTIONS.mode)
    
    return 0

if __name__ == '__main__':
    main()

