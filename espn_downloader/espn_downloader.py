#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
#  Copyright (c) 2013 Will Adams
#  Distributed under the terms of the Modified BSD License.
#  The full license is in the file LICENSE, distributed with this software.
#
#  I Would have never figured out how to make this work without
#  the espn3 xbmc addon by Ksosez/BlueCop. Thanks for that.


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
import numbers
import string

ESPN_USERDATA_URL = ('http://broadband.espn.go.com/espn3/auth/userData?'
                     'format=xml')
ESPN_CONFIG_URL = 'http://espn.go.com/watchespn/player/config'
FEEDS_URL_BASE = 'http://espn.go.com/watchespn/feeds/startup?action=replay'
LIVE_URL_BASE = 'http://espn.go.com/watchespn/feeds/startup?action=live'
AUTH_URL_BASE_HDS = ('https://espn-ws.bamnetworks.com/'
                     'pubajaxws/bamrest/MediaService2_0/'
                     'op-findUserVerifiedEvent/v-2.1')
AUTH_URL_BASE_HLS = ('http://broadband.espn.go.com/espn3/auth/'
                     'watchespn/startSession')
AUTH_URL_BASE = {'HLS': AUTH_URL_BASE_HLS,
                 'HDS': AUTH_URL_BASE_HDS,
                 'RTMP': AUTH_URL_BASE_HDS,}
NETWORK_IDS = {'n360': 'espn3',
               'n501': 'espn1',
               'n502': 'espn2',
               'n599': 'espnu',
               'goalline': 'goalline',
               'buzzerbeater': 'buzzerbeater'}


def get_options():
    parser = argparse.ArgumentParser(prog='espn_downloader')
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
    parser.add_argument('--download-dir', default=None,
                        help='Default: current directory')
    parser.add_argument('--cache-dir', default='~/.config/iz_espn',
                        help='Directory for storing/reading events cache.')
    parser.add_argument('-r', '--force-refresh-minutes', type=int, default=60)
    options = parser.parse_args()
    if options.download_dir is None:
        options.download_dir = os.getcwd()
    else:
        options.download_dir = os.path.expandvars(options.download_dir)
        options.download_dir = os.path.expanduser(options.download_dir)
    options.cache_dir = os.path.expandvars(options.cache_dir)
    options.cache_dir = os.path.expanduser(options.cache_dir)
    return options

OPTIONS = get_options()

def get_events(days=7, force_refresh_minutes=None, channels=['espn3'],
               mode='replay'):
    if mode == 'live':
        live_url = get_live_url()
        events = parse_feed(live_url)
        return events
    now = datetime.now()
    end = now + timedelta(days=1)
    start = now-timedelta(days)
    for c in channels:
        new_url = get_feeds_url(start, [c])
        print('Fetching new events from server...')
        events = parse_feed(new_url)
    events = sorted(events, key=lambda e: e['start_time'], reverse=True)
    events = filter_events(events)
    return events

def get_live_url(channels=['espn3']):
    channels = ','.join(channels)
    #~ start_date = start.strftime('%Y%m%d')
    #~ end_date = end.strftime('%Y%m%d')
    live_url = '{}&channel={}'.format(LIVE_URL_BASE,
                                                                channels)
    print('{1}\nLive URL: {0}\n{1}\n'.format(live_url, '='*78))
    return live_url

def get_feeds_url(start, channels=['espn3'], end=None):
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

def parse_feed(feed):
    if type(feed) == etree._Element:
        root = feed
    else:
        xml = etree.parse(feed)
        root = xml.getroot()
    events = [get_event_info(i) for i in root]
    events = sorted(events, key=lambda e: e['start_time'], reverse=True)
    return events

def get_event_info(event):
    event_info = dict(event.attrib)
    event_items = {item.tag: item.text for item in list(event)}
    event_info.update(event_items)
    start_timestamp = int(event_info['startTimeGmtMs']) / 1000
    start_time = datetime.fromtimestamp(start_timestamp)
    filename = sanitize_filename('{}-{}-{}'.format(
                                            event_info['sportDisplayValue'],
                                            event_info['name'],
                                            start_time.strftime('%Y.%m.%d'),))
    event_info['start_time'] = start_time
    event_info['filename'] = filename
    return event_info

def sanitize_filename(name, space_char='.'):
    #~ linux_invalid = [r'/']
    #~ windows_invalid = [r'<', r'>', r':', r'"', r'/', r'\', r'|', r'?', r'*']
    filename = name
    filename = re.sub(r' ', space_char, filename).strip(space_char)
    filename = re.sub(r'[:/\<>|*?]', ';', filename).strip(';')
    filename = re.sub('["\']', "", filename)
    return filename

def filter_events(events):
    events = filter_by_time(events)
    if OPTIONS.list_sports:
        events = prompt_sports(events)
    if OPTIONS.search:
        events = search_events(events, OPTIONS.search)
    return events

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

def search_events(events, regex):
    filtered = []
    for pat in regex:
        found = [i for i in events
                 if re.search(pat, i['xml'].xpath('string()'), re.I)]
        filtered.extend(found)
    return filtered

def prompt_events(events):
    #~ if not events:
        #~ print('No events to display with current options. Exiting...')
        #~ sys.exit()
    choices = ['{} {:^12} {:6} {}'.format(i['networkId'],
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

def prompt_user_list(choices, prompt=None,
                     header='User input required',
                     default=0, info=None,
                     include_quit=True, quit_def=('q', 'quit'),
                     lines_before=1,
                     header_sep='>', choices_sep='-', sep_length=78):
    print('\n'*lines_before)
    if header:
        if header_sep:
            print(header_sep*sep_length)
        print('{}:'.format(header))
        if header_sep:
            print(header_sep*sep_length)
    if prompt is None:
        prompt = 'Select from the choices above [{}]: '.format(default)
    idx_width = len(str(len(choices)))
    choices = '\n'.join(['{:{width}}) {}'.format(n, i, width=idx_width)
                         for n,i in enumerate(choices)])
    if include_quit:
        choices = '\n'.join([choices, '{}) {}'.format(*quit_def)])
    #~ if choices_sep:
        #~ print(choices_sep*sep_length)
    print(choices)
    if choices_sep:
        print(choices_sep*sep_length)
    while True:
        response = input(prompt).lower()
        if response == '':
            return default
        if response == 'q':
            return False
        if response.isdigit():
            response = int(response)
        if response in range(len(choices.splitlines())):
            return int(response)
        else:
            print('Invalid choice.')

def get_auth_url(event):
    stream_type = event['desktopStreamSource']
    network_info = get_network_info(event['networkId'])
    user_info = get_user_info()
    channel = network_info['channel']
    pkan = ''.join([random.choice(string.ascii_letters + string.digits)
                  for n in range(51)])
    pkan = '{}%3D'.format(pkan)
    auth_params = OrderedDict()
    if stream_type.lower() == 'hls':
        auth_params['v'] = '1.5'
        auth_params['affiliate'] = user_info['affiliate_name']
        auth_params['cdnName'] = network_info['cdnName']
        auth_params['channel'] = channel
        auth_params['playbackScenario'] = 'FMS_CLOUD'
        auth_params['pkan'] = pkan
        auth_params['pkanType'] = 'SWID'
        auth_params['eventid'] = event['id']
        auth_params['simulcastAiringId'] = event['simulcastAiringId']
        auth_params['rand'] = str(random.randint(100000,999999))
        auth_params['playerId'] = network_info['playerId']
    else:
        #auth_params['playbackScenario'] = 'FMS_CLOUD'
        #auth_params['channel'] = channel
        ##auth_params['partnerContentId'] = event['eventid']
        #auth_params['partnerContentId'] = event['id']
        ##auth_params['eventId'] = event['bamEventId']
        ##auth_params['contentId'] = event['bamContentId']
        #auth_params['eventId'] = event['eventId']
        #auth_params['contentId'] = event['bamContentId']
        #auth_params['rand'] = '{:.16f}'.format(random.random())
        #auth_params['cdnName'] = network_info['cdnName']
        #auth_params['identityPointId'] = user_info['identityPointId']
        #auth_params['playerId'] = network_info['playerId']
        raise
    auth_params_str = '&'.join(['='.join([k,v]) for k,v in
                                auth_params.items()])
    auth_url = '{}?{}'.format(AUTH_URL_BASE[stream_type], auth_params_str)
    print('{1}\nAuth URL: {0}\n{1}\n'.format(auth_url, '='*78), sep='\n')
    return auth_url

def get_network_info(channel='espn3'):
    xml = etree.parse(ESPN_CONFIG_URL)
    root = xml.getroot()
    #network = root.xpath('.//network[@name=$channel]', channel=channel)[0]
    network = root.xpath('.//network[@id=$channel]', channel=channel)[0]
    playerId = network.get('playerId')
    cdnName = network.get('defaultCdn')
    channel = network.get('name')
    network_info = {'playerId': playerId, 'cdnName': cdnName,
                    'channel': channel}
    print('{1}\nNetwork Info: {0}\n{1}\n'.format(network_info, '='*78),
          sep='\n')
    return network_info

def get_user_info():
    xml = etree.parse(ESPN_USERDATA_URL)
    root = xml.getroot()
    affiliate_name = root.find('affiliate/name').text
    swid = root.find('personalization').get('swid')
    identityPointId = ':'.join([affiliate_name, swid])
    return {'identityPointId': identityPointId,
            'affiliate_name': affiliate_name,
            'swid': swid}

def get_event(event, quality=None, mode='replay'):
    stream_type = event['desktopStreamSource']
    if stream_type.lower() == 'hls':
        ext = 'ts'
    else:
        ext = 'mp4'
    download_path = os.path.join(OPTIONS.download_dir, event['filename'])
    download_path = '{}.{}'.format(download_path, ext)
    auth_url = get_auth_url(event)
    smil_url = get_smil_url(auth_url)
    downloaded = download_stream(smil_url, download_path, stream_type)
    return downloaded

def get_smil_url(auth_url):
    xml = etree.parse(urllib.request.urlopen(auth_url))
    root = xml.getroot()
    # todo: find url tag
    smil_url = root.find('{*}user-verified-event/'
                    '{*}user-verified-content/'
                    '{*}user-verified-media-item/'
                    '{*}url').text
    print('{1}\nSMIL URL: {0}\n{1}\n'.format(smil_url, '='*78), sep='\n')
    return smil_url

def download_stream(smil_url, outfile, stream_type):
    if stream_type.lower() == 'hls':
        downloaded = download_hls(smil_url, outfile)
    else:
        downloaded = download_rtmp(smil_url, outfile)
    return downloaded

def download_hls(url, outfile):
    cmd = ['ffmpeg',
            '-i', url,
            '-c', 'copy',
            outfile]
    print('ffmpeg command:')
    print(' '.join(cmd))
    print('\n')
    o = subprocess.check_call(cmd,
                              #stderr=subprocess.DEVNULL,
                              #stdin=subprocess.DEVNULL
                             )
    return outfile

def download_rtmp(smil_url, outfile, mode='replay'):
    quality = select_bitrate(OPTIONS.bitrate)
    rtmp_info = get_rtmp_info(smil_url, quality=quality)
    if mode == 'replay':
        url = '{}/?{}'.format(rtmp_info['rtmp_url'], rtmp_info['rtmp_auth'])
        playpath = rtmp_info['playpath']
    else:
        url = rtmp_info['rtmp_url']
        playpath = '{}?{}'.format(rtmp_info['playpath'],
                                  rtmp_info['rtmp_auth'])
    args = ['rtmpdump', '-r', url,
            '-y', playpath, '-m', '360']
            #~ '-e', '-o', path]
    if mode == 'replay':
        args.extend(['-e', '-o', outfile])
    else:
        args.extend(['-v', '-Y', '-o', outfile])

    print('{1}\nRTMP cmd: {0}\n{1}\n'.format(' '.join(args), '='*78), sep='\n')
    ret_code = 1
    tries = 0
    while ret_code != 0 and tries <= 100:
        ret_code = subprocess.call(args)
        tries += 1
        time.sleep(.2)
    return path

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
    print('{1}\nBitrate: {0:.0f}k\n{1}\n'.format(
                            video_bitrates[bitrate]/1000, '='*78), sep='\n')
    return bitrate

def get_rtmp_info(smil_url, quality=None):
    rtmp_auth = smil_url.partition('?')[2]
    xml = etree.parse(urllib.request.urlopen('{}&{:.16f}'.format(smil_url,
                                                             random.random())))
    root = xml.getroot()
    video_streams = root.findall('body/switch/video')
    stream = video_streams[quality]
    print(etree.tostring(stream, pretty_print=True).decode())
    playpath = stream.get('src')
    rtmp_url_base = root.find('head/meta').get('base')
    rtmp_info = {'rtmp_url': rtmp_url_base, 'playpath': playpath,
                 'rtmp_auth': rtmp_auth}
    print('{1}\nRTMP Info: {0}\n{1}\n'.format(rtmp_info, '='*78), sep='\n')
    return rtmp_info


def main(mode='replay'):
    events = get_events(OPTIONS.days)
    chosen = prompt_events(events)
    print('{1}\nEvent Info: {0}\n{1}\n'.format(chosen, '='*78), sep='\n')
    #~ quality = select_bitrate(OPTIONS.bitrate)
    downloaded = get_event(chosen, quality=OPTIONS.bitrate)
    
    return 0

if __name__ == '__main__':
    main()

