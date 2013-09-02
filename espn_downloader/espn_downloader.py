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

def get_event_info(event):
    eventid = event.get('id')
    bamContentId = event.get('bamContentId')
    bamEventId = event.get('bamEventId')
    name = event.find('name').text
    event = {'eventid': eventid, 'bamContentId': bamContentId, 
             'bamEventId':bamEventId, 'name': name}
    return event
    
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


def main():
    get_user_info()
    return 0

if __name__ == '__main__':
    main()

