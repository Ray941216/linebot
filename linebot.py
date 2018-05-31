from flask import Flask, url_for, request, abort, jsonify
import pymysql
from math import *
import requests as rqs
from numpy import average as avg
import subprocess as spcss
from time import time as timestamper
import numpy as np
from geopy.geocoders import Nominatim
from datetime import datetime, timedelta
from weather import Weather, Unit

_DEBUGGING_ = True

# geopy geoencoder
geolocator = Nominatim()

db = pymysql.connect("localhost", "linebot", "linbotoffatcat", "linebot", port = 3307, use_unicode=True, charset="utf8")
cursor = db.cursor()

# using to get keys from database
sql = "SELECT `key_ptn` FROM `key_pad` WHERE name = %s"

# Open Weather Map
cursor.execute(sql, ('OWM_KEY'))
k = cursor.fetchall()
OWM_KEY = k[0][0]

# Open Weather Map Official
cursor.execute(sql, ('OWM_KEY_official'))
k = cursor.fetchall()
OWM_KEY_official = k[0][0]

# Google Geoencode API
cursor.execute(sql, ('GEOCODE_KEY'))
k = cursor.fetchall()
GEOCODE_KEY = k[0][0]

db.close()

if _DEBUGGING_:
    print(OWM_KEY, OWM_KEY_official, GEOCODE_KEY)

# last update gov place data time
LAST_UPDATE = datetime.now().timestamp()

if not _DEBUGGING_:
    try:
        print(spcss.run("python openplacetosql.py".split(" ")))
    except spcss.CalledProcessError:
        print(spcss.CalledProcessError)
    except Exception as e:
        print(str(e))


def geo_encode(place_name):
    print("geo_encode:", place_name)
    geo = {
        "found": False,
        "name": "",
        "lat": "",
        "lon": ""
    }
    dbres = {
        "lon": [],
        "lat": [],
        "name": []
    }
    found = False
    dup = False

    db = pymysql.connect("localhost", "linebot", "linbotoffatcat", "linebot", port = 3307, use_unicode=True, charset="utf8")
    cursor = db.cursor()
    # 先查政府資料
    sql = "SELECT AVG(lon) lon, AVG(lat) lat FROM `place` WHERE keyword LIKE '{0}' OR name LIKE '{0}' OR addr LIKE '{0}'"
    search = "%"
    for s in place_name:
        search += s + "%"

    print("geo_encode-place:", sql.format(search))

    cursor.execute(sql.format(search))
    dbrec = cursor.fetchall()
    if dbrec[0][0] != None and dbrec[0][1] != None:
        found = True

        for r in dbrec:
            dbres['lon'].append(r[0])
            dbres['lat'].append(r[1])
            dbres['name'].append(place_name)

    # 接著查我的資料
    if not found:
        sql = "SELECT AVG(lon) lon, AVG(lat) lat FROM `myplace` WHERE name LIKE '{}'"
        print("geo_encode-myplace:", sql.format(search))
        cursor.execute(sql.format(search))
        dbrec = cursor.fetchall()

        if dbrec[0][0] != None and dbrec[0][1] != None:
            found = True

            for r in dbrec:
                dbres['lon'].append(r[0])
                dbres['lat'].append(r[1])
                dbres['name'].append(place_name)

    # 查詢 Nominatim
    if not found:
        loc = geolocator.geocode("{} 台灣".format(place_name))
        if loc != None:
            found = True
            sql = "INSERT INTO `myplace`(`lat`, `lon`, `name`, `addr`) VALUES ('{}', '{}', '{}', '{}')"
            try:
                cursor.execute(sql.format(loc.latitude, loc.longitude, place_name, loc.address))
                db.commit()
            except Exception as e:
                db.rollback()
                with open("loggeo.txt", 'a+') as f:
                    f.write(sql)
                    f.write('\n')
                    f.write(str(e))
                    f.write('\n')
            dbres['lon'].append(loc.longitude)
            dbres['lat'].append(loc.latitude)
            dbres['name'].append(loc.address)


    # 再透過 geo encode 查詢
    if not found:
        s = rqs.get("https://maps.googleapis.com/maps/api/geocode/json?address={}&key={}&language=zh-TW".format(place_name, GEOCODE_KEY))
        ans = s.json()
        try:
            print("Len:",len(ans['results']), "Stat:", ans['status'])
        except:
            print("Error", ans)
        if len(ans['results']) > 0:
            found = True
            if len(ans['results']) > 1:
                dup = True
            for r in ans['results']:
                sql = "INSERT INTO `myplace`(`lat`, `lon`, `name`, `addr`) VALUES ('{}', '{}', '{}', '{}')"
                try:
                    cursor.execute(sql.format(r['geometry']['location']['lat'], r['geometry']['location']['lng'], place_name, r['formatted_address']))
                    db.commit()
                except Exception as e:
                    db.rollback()
                    with open("loggeo.txt", 'a+') as f:
                        f.write(sql)
                        f.write('\n')
                        f.write(str(e))
                        f.write('\n')

                dbres['lon'].append(r['geometry']['location']['lng'])
                dbres['lat'].append(r['geometry']['location']['lat'])
                dbres['name'].append(r['formatted_address'])


    # 製作回傳資料
    if found:
        if dup:
            geo['found'] = found
            geo['name'] = place_name
            geo['lat'] = np.around(np.average(dbres['lat']), 6)
            geo['lon'] = np.around(np.average(dbres['lon']), 6)
        else:
            geo['found'] = found
            geo['name'] = dbres['name'][0]
            geo['lat'] = float(dbres['lat'][0])
            geo['lon'] = float(dbres['lon'][0])
    db.close()

    print("geo_encode-return:", geo)
    return geo


def feeling_temp(temp, wind, humidity):
    wpa = (humidity / 100) * 6.105 * np.exp((17.27 * temp) / (237.7 + temp))
    ftemp = 1.07 * temp + 0.2 * wpa - 0.65 * wind - 2.7
    feel = "酷熱" if ftemp > 32 else "熱" if ftemp > 30 else "微熱" if ftemp > 27 else "舒適" if ftemp >= 20 else "微冷" if ftemp > 18 else "冷" if ftemp >= 11 else "寒冷"

    out = {
        "feeling_temp": np.around(ftemp, decimals=1),
        "feel": feel
    }
    return out


def weather_query(geo, period):
    print("weather_query:", geo, period)
    now = datetime.now()
    '''
        2006    # year [0]
        11      # month [1]
        21      # day [2]
        16      # hour [3]
        30      # minute [4]
        0       # second [5]
        1       # weekday (0 = Monday) [6]
        325     # number of days since 1st January
        -1      # dst - method tzinfo.dst() returned None
    '''
    now = now.timetuple()
    print("weather_query-now_tuple6:", now[6])


    work = "forcast/daily"
    day_dist = 1
    if period in ['現在']:
        work = "weather"
        day_dist = 0
    else:
        f = lambda d, n: d + n if d + n < 7 else f(d, n - 6)
        for x, n in zip(['週一', '週二', '週三', '週四', '週五', '週六', '週日', '週末', '明天', '後天', '今天'], [0, 1, 2, 3, 4, 5, 6, 6, f(now[6], 1), f(now[6], 2), f(now[6], 0)]):
            if period == x:
                day_dist = abs(n - now[6])
                break

        for x, n in zip(['兩天後', '三天後', '四天後', '五天後', '六天後', '七天後', '八天後', '九天後', '十天後'], [f(now[6], i+1) for i in range(2, 11)]):
            if period == x:
                day_dist = abs(n - now[6])
                break
    print("weather_query-work/day_dist", work, day_dist)
    out = {
        'work': "",
        'ans': None
    }
    if work != "NOT-AVAILABLE":
        db = pymysql.connect("localhost", "linebot", "linbotoffatcat", "linebot", port = 3307, use_unicode=True, charset="utf8")
        cursor = db.cursor()
        if work == "weather":
            s = rqs.get("https://api.openweathermap.org/data/2.5/{}?APPID={}&lat={}&lon={}&units=metric&lang=zh_tw".format(work, OWM_KEY, geo['lat'], geo['lon']))
        else:
            sql_dist = "SELECT id, ( 6371 * acos( cos( radians({0}) ) * cos( radians( lat ) ) * cos( radians( lon ) - radians({1}) ) + sin( radians({0}) ) * sin( radians( lat ) ) ) ) AS distance FROM city ORDER BY distance LIMIT 1"
            cursor.execute(sql_dist.format(geo['lat'], geo['lon']))
            city = cursor.fetchall()
            s = rqs.get("https://openweathermap.org/data/2.5/forecast/daily?appid={}&id={}&units=metric".format(OWM_KEY_official, city[0][0]))
        wres = s.json()
        if _DEBUGGING_:
            print("weather_query-wres:", wres)

        if str(wres['cod']) == '200':
            if work == "forcast/daily":
                if period == "這週":
                    out['ans'] = wres['list'][1:7 - now[6]]
                elif period == "週末":
                    out['ans'] = wres['list'][5 - now[6]:7 - now[6]]
                    pass
                else:
                    out['ans'] = [wres['list'][day_dist]]

                for i_o, o in enumerate(out['ans']):
                    sql_desc = "SELECT `description` FROM `weather_cond` WHERE `id` = {}"
                    l = cursor.execute(sql_desc.format(o['weather'][0]['id']))
                    if l > 0:
                        wc = cursor.fetchall()
                        desc = wc[0][0]
                    else:
                        desc = o['weather'][0]['description']
                    out['ans'][i_o]['weather'][0]['description'] = desc
                    out['ans'][i_o]['weather'][0].update({'img':'https://openweathermap.org/img/w/{}.png'.format(o['weather'][0]['icon'])})

            elif work == "weather":
                sql_desc = "SELECT `description` FROM `weather_cond` WHERE `id` = {}"
                l = cursor.execute(sql_desc.format(wres['weather'][0]['id']))
                if l > 0:
                    wc = cursor.fetchall()
                    desc = wc[0][0]
                else:
                    desc = wres['weather'][0]['description']
                    sql = "INSERT INTO `weather_cond`(`id`, `description`) VALUES (%s,%s)"
                    cursor.execute(sql, (wres['weather'][0]['id'], wres['weather'][0]['description']))
                    cursor.commit()


                out['ans'] = {
                    'description': desc,
                    'img': 'https://openweathermap.org/img/w/{}.png'.format(wres['weather'][0]['icon']),
                    'clouds': wres['clouds']['all'],
                    'humidity': wres['main']['humidity'],
                    'temp': wres['main']['temp'],
                    'temp_max': wres['main']['temp_max'],
                    'temp_min': wres['main']['temp_min'],
                    'wind': wres['wind']['speed'],
                    'visibility': wres['visibility']
                }
            db.close()
        else:
            work = "NOT-AVAILABLE"
    out['work'] = work
    if _DEBUGGING_:
        print("weather_query-return:", out)

    return out

app = Flask(__name__)
app.config['SECRET_KEY'] = 'linbotoffatcat'

@app.route('/callback', methods=['GET','POST'])
def webhook():
    rcv_dt = datetime.now()
    rcv_timestamp = timestamper()

    if request.method == 'POST' and request.headers['fullfillment'] == '201805202047':
        data = request.get_json(force=True)
        db = pymysql.connect("localhost", "linebot", "linbotoffatcat", "linebot", port = 3307, use_unicode=True, charset="utf8")
        cursor = db.cursor()
        template = {
            "fulfillmentMessages": [],
            "payload": {},
            "outputContexts": (data['queryResult']['outputContexts'] if 'outputContexts' in data['queryResult'] else []),
            "fulfillmentText": "發生錯誤！"
        }
        noRecord = False
        if data['queryResult']['intent']['displayName'] not in ['edit_user_info']:
            # 檢查送來的請求有無使用者資訊
            notIn = True
            idx = -1
            for i_c, c in enumerate(template['outputContexts']):
                if c['name'] == "{}/contexts/user".format(data['session']):
                    notIn = False
                    idx = i_c
                    break

            sql = "SELECT users.name, users.gender, users.home FROM users WHERE users.u_id='{}' AND users.plaform ='{}'"
            if 'source' in data['originalDetectIntentRequest']: # from other integration
                l = cursor.execute(sql.format(data['originalDetectIntentRequest']['payload']['source'][data['originalDetectIntentRequest']['payload']['source']['type']+'Id'], data['originalDetectIntentRequest']['source']))
            else: # from console
                l = cursor.execute(sql.format('superuser', 'console'))

            if l == 0:
                noRecord = True
                print("[INFO] GOT A NO DETAIL USER!")
            else:
                res = cursor.fetchall()
                res = [list(x) for x in res]
                if res[0][0] in ['', None]:
                    noRecord = True

                if not noRecord:
                    print("An old user access!")
                    res[0][1] = "女" if res[0][1] == 0 else "男" if res[0][1] == 1 else "群組"
                    if notIn:
                        tmp = {
                            "name": "{}/contexts/user".format(data['session']),
                            "lifespanCount": 1410065407,
                            "parameters": {
                                "name.original": "",
                                "gender": "",
                                "name": "",
                                "home.original": "",
                                "gender.original": "",
                                "home": ""
                            }
                        }
                        template['outputContexts'].append(tmp)

                    for i_e, expr in enumerate(['name', 'gender', 'home']):
                        for k in template['outputContexts'][idx]['parameters'].keys():
                            if k.find(expr) > -1 :
                                template['outputContexts'][idx]['parameters'][k] = res[0][i_e]
        db.close()
        if _DEBUGGING_:
            print(data)

        action_code = 0

        if data['queryResult']['intent']['displayName'] in ['Default_Welcome_hello', 'edit_user_info']:
            if data['queryResult']['parameters']['name'] == "" or data['queryResult']['parameters']['gender'] == "" or data['queryResult']['parameters']['home'] == "":
                template['fulfillmentText'] = data['queryResult']['fulfillmentText']
                if not noRecord:
                    template['fulfillmentText'] = "你好呀！ {}\n你如果剛剛有問我問題，請你再問我一次~".format(res[0][0])
                    if 'source' in data['originalDetectIntentRequest'] and data['originalDetectIntentRequest']['source'] == "group":
                        template['fulfillmentText'] = ""
            else:
                if noRecord or data['queryResult']['intent']['displayName'] == 'edit_user_info':
                    action_code = 1
                    template['fulfillmentText'] = data['queryResult']['fulfillmentText']
                else:
                    action_code = 0
                    template['fulfillmentText'] = "住在 {} 的 {} 歡迎使用本執事服務，您可以跟我聊天、問天氣、叫我算數學⋯⋯等".format(res[0][2], res[0][1])

        elif data['queryResult']['intent']['displayName'] == 'playmath':
            if data['queryResult']['parameters']['math-str'] != '':
                math_exp = data['queryResult']['queryText']
                math_exp2 = data['queryResult']['queryText']
                math_op2 = math_exp2.split('\n')
                while math_exp2.find('=') > -1:
                    math_exp2 = math_exp2.replace('=', "")

                ptn = ['(', ")", '＾', '^', '[', ']', '{', '}', '=', "（", "）", "＋", "－", "＊", "／", "π", "加", "減", "乘", "除", "一", "二", "三", "四", "五", "六", "七", "八", "九", "十", "百", "千", "萬"]
                rightptn = ["（（", "））", "**", "**", "(", ")", "(", ")", "", "(", ")", "+", "-", "*", "/", "(pi)", "+", "-", "*", "/", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "*100", "*1000", "*10000"]
                for p, r in zip(ptn, rightptn):
                    while math_exp.find(p) > -1:
                        math_exp = math_exp.replace(p, r)
                math_op = math_exp.split('\n')
                math_ans = []
                for i_op, mop in enumerate(math_op):
                    try:
                        print(i_op, mop)
                        ans = eval(mop.lower())
                        print(ans)
                        math_ans.append(ans)
                    except:
                        math_ans.append(data['queryResult']['fulfillmentText'])

                str2 = "({}): {} = {}"
                template['fulfillmentText'] = ""
                for i_op, (expr, ans) in enumerate(zip(math_op2, math_ans)):
                    if i_op > 0:
                        template['fulfillmentText'] += '\n'
                    template['fulfillmentText'] += str2.format(i_op + 1, expr, ans)
        elif data['queryResult']['intent']['displayName'] == 'smalltalk.greetings.goodmorning':
            action_code = 2
            period = "今天"
            task = "天氣"
            place = res[0][2]
            geo = geo_encode(place)
            ans = weather_query(geo, period)
            template['fulfillmentText'] = "早安！\n{}{}的{}預報如下：\n".format(period, place, task)
            for i, w in enumerate(ans['ans']):
                template['fulfillmentText'] += "概況：{}\n".format(w['weather'][0]['description'])
                f = feeling_temp(np.average([w['temp']['max'], w['temp']['min'], w['temp']['morn'], w['temp']['day'], w['temp']['eve'], w['temp']['night']]), w['speed'], w['humidity'])
                template['fulfillmentText'] += "平均體感氣溫：{}度（{}）\n".format(f['feeling_temp'], f['feel'])
                template['fulfillmentText'] += "最高氣溫：{}度\n".format(w['temp']['max'])
                template['fulfillmentText'] += "最低氣溫：{}度\n".format(w['temp']['min'])
                template['fulfillmentText'] += "清晨氣溫：{}度\n".format(w['temp']['morn'])
                template['fulfillmentText'] += "白天氣溫：{}度\n".format(w['temp']['day'])
                template['fulfillmentText'] += "傍晚氣溫：{}度\n".format(w['temp']['eve'])
                template['fulfillmentText'] += "夜晚氣溫：{}度\n".format(w['temp']['night'])
                template['fulfillmentText'] += "濕度：{}％\n".format(w['humidity'])
                template['fulfillmentText'] += "雲層覆蓋率：{}％\n".format(w['clouds'])
                template['fulfillmentText'] += "風速：{}公尺/秒\n".format(w['speed'])
        elif data['queryResult']['intent']['displayName'] in ['playnearbygoods', 'playnearbygoods - next']:
            next = int(eval(data['queryResult']['parameters']['next']))
            place = data['queryResult']['parameters']['place']
            try:
                km = float(data['queryResult']['parameters']['near-by-n-km'])
            except:
                for n, x in zip([1,2,3,4,5,6,7,8,9,10], ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十"]):
                    if data['queryResult']['parameters']['near-by-n-km'] == x:
                        km = n
                        break
            finally:
                if km in ["", None]:
                    km = 5
                    
            if place in ["", None]:
                if res[0][2] not in ["", None]:
                    place = res[0][2]
            if place == "":
                template['fulfillmentText'] = "很抱歉，我不知道您現在的位置，您可以先讓我認識您(說：嗨)以後再詢問！"
                pass
            else:
                template['fulfillmentText'] = "很抱歉，您輸入的公里數無效，使用預設值\n"
                geo = geo_encode(place)
                db = pymysql.connect("localhost", "linebot", "linbotoffatcat", "linebot", port = 3307, use_unicode=True, charset="utf8")
                cursor = db.cursor()
                sql = "SELECT name, ( 6371 * acos( cos( radians(%s) ) * cos( radians( lat ) ) * cos( radians( lon ) - radians(%s) ) + sin( radians(%s) ) * sin( radians( lat ) ) ) ) AS distance FROM place HAVING distance <= %s ORDER BY distance;"
                print((geo['lat'], geo['lon'], geo['lat'], data['queryResult']['parameters']['near-by-n-km']))
                l = cursor.execute(sql, (geo['lat'], geo['lon'], geo['lat'], km))
                if l > 0:
                    action_code = 3
                    pres = cursor.fetchall()
                    if next * 10 >= len(pres):
                        template['fulfillmentText'] = "沒有了"
                    else:
                        template['fulfillmentText'] = "{}附近{}公里內的景點總數{}個，目前顯示{}~{}筆，説「下一頁」來查看更多：\n".format(place, data['queryResult']['parameters']['near-by-n-km'], l, next * 10 + 1, min((next + 1) * 10, l))
                        for i_p, p in enumerate(pres):
                            if i_p > next * 10:
                                if i_p > (next + 1) * 10:
                                    break
                                template['fulfillmentText'] += "{}. {}({}km)\n".format(i_p, p[0], round(float(p[1]), 2))
                else:
                    template['fulfillmentText'] = data['queryResult']['fulfillmentText']
                db.close()
        elif data['queryResult']['intent']['displayName'] == 'playweather':
            period = data['queryResult']['parameters']['period']
            if period == "":
                period = "現在"
            task = data['queryResult']['parameters']['task']
            if task == "":
                task = "天氣"
            place = data['queryResult']['parameters']['place']
            if place in ["", None, "外面", "室外", "外頭"]:
                if res[0][2] not in ["", None]:
                    place = res[0][2]
            print("playweather:",period,task,place)
            if place == "":
                template['fulfillmentText'] = "很抱歉，我不知道您現在的位置，您可以先讓我認識您(說：嗨)以後再詢問！"
                pass
            else:
                geo = geo_encode(place)
                print(geo)
                if geo['found']:
                    # call 天氣 API
                    ans = weather_query(geo, period)
                    action_code = 2
                    if ans['work'] == "NOT-AVAILABLE":
                        action_code = 0
                        template['fulfillmentText'] = "很抱歉，我找不到\n{}\n的天氣資料，可能是有多個位置具有相同名稱，可以試試看用更精確的說法來查詢。".format(place)
                    elif task == "天氣":
                        now = datetime.now()
                        '''
                            2006    # year [0]
                            11      # month [1]
                            21      # day [2]
                            16      # hour [3]
                            30      # minute [4]
                            0       # second [5]
                            1       # weekday (0 = Monday) [6]
                            325     # number of days since 1st January
                            -1      # dst - method tzinfo.dst() returned None
                        '''
                        weekday = ['週一', '週二', '週三', '週四', '週五', '週六', '週日']
                        if type(ans['ans']) == type([]):
                            # forcast
                            template['fulfillmentText'] = "{}{}的{}預報如下：\n".format(period, place, task)
                            if period == "週末":
                                for i, w in enumerate(ans['ans']):
                                    if i > 0:
                                        template['fulfillmentText'] += "\n"
                                    nextD = now +timedelta(days = i+(5 - now.timetuple()[6]))
                                    template['fulfillmentText'] += "{}月{}日（{}）\n".format(nextD.timetuple()[1], nextD.timetuple()[2],weekday[nextD.timetuple()[6]])
                                    template['fulfillmentText'] += "概況：{}\n".format(w['weather'][0]['description'])
                                    f = feeling_temp(np.average([w['temp']['max'], w['temp']['min'], w['temp']['morn'], w['temp']['day'], w['temp']['eve'], w['temp']['night']]), w['speed'], w['humidity'])
                                    template['fulfillmentText'] += "平均體感氣溫：{}度（{}）\n".format(f['feeling_temp'], f['feel'])
                                    template['fulfillmentText'] += "最高氣溫：{}度\n".format(w['temp']['max'])
                                    template['fulfillmentText'] += "最低氣溫：{}度\n".format(w['temp']['min'])
                                    template['fulfillmentText'] += "清晨氣溫：{}度\n".format(w['temp']['morn'])
                                    template['fulfillmentText'] += "白天氣溫：{}度\n".format(w['temp']['day'])
                                    template['fulfillmentText'] += "傍晚氣溫：{}度\n".format(w['temp']['eve'])
                                    template['fulfillmentText'] += "夜晚氣溫：{}度\n".format(w['temp']['night'])
                                    template['fulfillmentText'] += "濕度：{}％\n".format(w['humidity'])
                                    template['fulfillmentText'] += "雲層覆蓋率：{}％\n".format(w['clouds'])
                                    template['fulfillmentText'] += "風速：{}公尺/秒\n".format(w['speed'])
                            elif period == "這週":
                                for i, w in enumerate(ans['ans']):
                                    if i > 0:
                                        template['fulfillmentText'] += "\n"
                                    nextD = now +timedelta(days = i+1)
                                    template['fulfillmentText'] += "{}月{}日（{}）\n".format(nextD.timetuple()[1], nextD.timetuple()[2],weekday[nextD.timetuple()[6]])
                                    template['fulfillmentText'] += "概況：{}\n".format(w['weather'][0]['description'])
                                    f = feeling_temp(np.average([w['temp']['max'], w['temp']['min'], w['temp']['morn'], w['temp']['day'], w['temp']['eve'], w['temp']['night']]), w['speed'], w['humidity'])
                                    template['fulfillmentText'] += "平均體感氣溫：{}度（{}）\n".format(f['feeling_temp'], f['feel'])
                                    template['fulfillmentText'] += "最高氣溫：{}度\n".format(w['temp']['max'])
                                    template['fulfillmentText'] += "最低氣溫：{}度\n".format(w['temp']['min'])
                                    template['fulfillmentText'] += "清晨氣溫：{}度\n".format(w['temp']['morn'])
                                    template['fulfillmentText'] += "白天氣溫：{}度\n".format(w['temp']['day'])
                                    template['fulfillmentText'] += "傍晚氣溫：{}度\n".format(w['temp']['eve'])
                                    template['fulfillmentText'] += "夜晚氣溫：{}度\n".format(w['temp']['night'])
                                    template['fulfillmentText'] += "濕度：{}％\n".format(w['humidity'])
                                    template['fulfillmentText'] += "雲層覆蓋率：{}％\n".format(w['clouds'])
                                    template['fulfillmentText'] += "風速：{}公尺/秒\n".format(w['speed'])
                            else:
                                for i, w in enumerate(ans['ans']):
                                    if i > 0:
                                        template['fulfillmentText'] += "\n"
                                    template['fulfillmentText'] += "概況：{}\n".format(w['weather'][0]['description'])
                                    f = feeling_temp(np.average([w['temp']['max'], w['temp']['min'], w['temp']['morn'], w['temp']['day'], w['temp']['eve'], w['temp']['night']]), w['speed'], w['humidity'])
                                    template['fulfillmentText'] += "平均體感氣溫：{}度（{}）\n".format(f['feeling_temp'], f['feel'])
                                    template['fulfillmentText'] += "最高氣溫：{}度\n".format(w['temp']['max'])
                                    template['fulfillmentText'] += "最低氣溫：{}度\n".format(w['temp']['min'])
                                    template['fulfillmentText'] += "清晨氣溫：{}度\n".format(w['temp']['morn'])
                                    template['fulfillmentText'] += "白天氣溫：{}度\n".format(w['temp']['day'])
                                    template['fulfillmentText'] += "傍晚氣溫：{}度\n".format(w['temp']['eve'])
                                    template['fulfillmentText'] += "夜晚氣溫：{}度\n".format(w['temp']['night'])
                                    template['fulfillmentText'] += "濕度：{}％\n".format(w['humidity'])
                                    template['fulfillmentText'] += "雲層覆蓋率：{}％\n".format(w['clouds'])
                                    template['fulfillmentText'] += "風速：{}公尺/秒\n".format(w['speed'])
                        else:
                            # current
                            template['fulfillmentText'] = "{}{}的{}資訊如下：\n".format(period, place, task)
                            template['fulfillmentText'] += "概況：{}\n".format(ans['ans']['description'])
                            f = feeling_temp(ans['ans']['temp'], ans['ans']['wind'], ans['ans']['humidity'])
                            template['fulfillmentText'] += "目前體感氣溫：{}度（{}）\n".format(f['feeling_temp'], f['feel'])
                            template['fulfillmentText'] += "目前氣溫：{}度\n".format(ans['ans']['temp'])
                            template['fulfillmentText'] += "最高氣溫：{}度\n".format(ans['ans']['temp_max'])
                            template['fulfillmentText'] += "最低氣溫：{}度\n".format(ans['ans']['temp_min'])
                            template['fulfillmentText'] += "濕度：{}％\n".format(ans['ans']['humidity'])
                            template['fulfillmentText'] += "雲層覆蓋率：{}％\n".format(ans['ans']['clouds'])
                            template['fulfillmentText'] += "目前風速：{}公尺/秒\n".format(ans['ans']['wind'])
                            # template['fulfillmentMessages'].append({"text":[{"text": template['fulfillmentText']}]})
                            # template['fulfillmentMessages'].append({"image":[{"imageUrl":ans['ans']['img'], "plaform":"line", "type":3}]})
                    elif task == "氣溫":
                        if type(ans['ans']) == 'list':
                            # forcast
                            template['fulfillmentText'] = "{}{}的{}預報如下：\n".format(period, place, task)
                            if period == "週末":
                                for i, w in enumerate(ans['ans']):
                                    if i > 0:
                                        template['fulfillmentText'] += "\n"
                                    nextD = now +timedelta(days = i+(5 - now.timetuple()[6]))
                                    template['fulfillmentText'] += "{}月{}日（{}）\n".format(nextD.timetuple()[1], nextD.timetuple()[2],weekday[nextD.timetuple()[6]])
                                    f = feeling_temp(np.average([w['temp']['max'], w['temp']['min'], w['temp']['morn'], w['temp']['day'], w['temp']['eve'], w['temp']['night']]), w['speed'], w['humidity'])
                                    template['fulfillmentText'] += "平均體感氣溫：{}度（{}）\n".format(f['feeling_temp'], f['feel'])
                                    template['fulfillmentText'] += "最高氣溫：{}度\n".format(w['temp']['max'])
                                    template['fulfillmentText'] += "最低氣溫：{}度\n".format(w['temp']['min'])
                                    template['fulfillmentText'] += "清晨氣溫：{}度\n".format(w['temp']['morn'])
                                    template['fulfillmentText'] += "白天氣溫：{}度\n".format(w['temp']['day'])
                                    template['fulfillmentText'] += "傍晚氣溫：{}度\n".format(w['temp']['eve'])
                                    template['fulfillmentText'] += "夜晚氣溫：{}度\n".format(w['temp']['night'])
                            elif period == "這週":
                                for i, w in enumerate(ans['ans']):
                                    if i > 0:
                                        template['fulfillmentText'] += "\n"
                                    nextD = now +timedelta(days = i+1)
                                    template['fulfillmentText'] += "{}月{}日（{}）\n".format(nextD.timetuple()[1], nextD.timetuple()[2],weekday[nextD.timetuple()[6]])
                                    f = feeling_temp(np.average([w['temp']['max'], w['temp']['min'], w['temp']['morn'], w['temp']['day'], w['temp']['eve'], w['temp']['night']]), w['speed'], w['humidity'])
                                    template['fulfillmentText'] += "平均體感氣溫：{}度（{}）\n".format(f['feeling_temp'], f['feel'])
                                    template['fulfillmentText'] += "最高氣溫：{}度\n".format(w['temp']['max'])
                                    template['fulfillmentText'] += "最低氣溫：{}度\n".format(w['temp']['min'])
                                    template['fulfillmentText'] += "清晨氣溫：{}度\n".format(w['temp']['morn'])
                                    template['fulfillmentText'] += "白天氣溫：{}度\n".format(w['temp']['day'])
                                    template['fulfillmentText'] += "傍晚氣溫：{}度\n".format(w['temp']['eve'])
                                    template['fulfillmentText'] += "夜晚氣溫：{}度\n".format(w['temp']['night'])
                            else:
                                for i, w in enumerate(ans['ans']):
                                    if i > 0:
                                        template['fulfillmentText'] += "\n"
                                    template['fulfillmentText'] += "{}月{}日（{}）\n".format(nextD.timetuple()[1], nextD.timetuple()[2],weekday[nextD.timetuple()[6]])
                                    f = feeling_temp(np.average([w['temp']['max'], w['temp']['min'], w['temp']['morn'], w['temp']['day'], w['temp']['eve'], w['temp']['night']]), w['speed'], w['humidity'])
                                    template['fulfillmentText'] += "平均體感氣溫：{}度（{}）\n".format(f['feeling_temp'], f['feel'])
                                    template['fulfillmentText'] += "最高氣溫：{}度\n".format(w['temp']['max'])
                                    template['fulfillmentText'] += "最低氣溫：{}度\n".format(w['temp']['min'])
                                    template['fulfillmentText'] += "清晨氣溫：{}度\n".format(w['temp']['morn'])
                                    template['fulfillmentText'] += "白天氣溫：{}度\n".format(w['temp']['day'])
                                    template['fulfillmentText'] += "傍晚氣溫：{}度\n".format(w['temp']['eve'])
                                    template['fulfillmentText'] += "夜晚氣溫：{}度\n".format(w['temp']['night'])
                        else:
                            # current
                            template['fulfillmentText'] = "{}{}的{}資訊如下：\n".format(period, place, task)
                            f = feeling_temp(ans['ans']['temp'], ans['ans']['wind'], ans['ans']['humidity'])
                            template['fulfillmentText'] += "目前體感氣溫：{}度（{}）\n".format(f['feeling_temp'], f['feel'])
                            template['fulfillmentText'] += "目前氣溫：{}度\n".format(ans['ans']['temp'])
                            template['fulfillmentText'] += "最高氣溫：{}度\n".format(ans['ans']['temp_max'])
                            template['fulfillmentText'] += "最低氣溫：{}度\n".format(ans['ans']['temp_min'])
                    elif task == "濕度":
                        if type(ans['ans']) == 'list':
                            # forcast
                            template['fulfillmentText'] = "{}{}的{}預報如下：\n".format(period, place, task)
                            if period == "週末":
                                for i, w in enumerate(ans['ans']):
                                    if i > 0:
                                        template['fulfillmentText'] += "\n"
                                    nextD = now +timedelta(days = i+(5 - now.timetuple()[6]))
                                    template['fulfillmentText'] += "{}月{}日（{}）\n".format(nextD.timetuple()[1], nextD.timetuple()[2],weekday[nextD.timetuple()[6]])
                                    template['fulfillmentText'] += "濕度：{}％\n".format(w['humidity'])
                            elif period == "這週":
                                for i, w in enumerate(ans['ans']):
                                    if i > 0:
                                        template['fulfillmentText'] += "\n"
                                    nextD = now +timedelta(days = i+1)
                                    template['fulfillmentText'] += "{}月{}日（{}）\n".format(nextD.timetuple()[1], nextD.timetuple()[2],weekday[nextD.timetuple()[6]])
                                    template['fulfillmentText'] += "濕度：{}％\n".format(w['humidity'])
                            else:
                                for i, w in enumerate(ans['ans']):
                                    if i > 0:
                                        template['fulfillmentText'] += "\n"
                                    template['fulfillmentText'] += "濕度：{}％\n".format(w['humidity'])
                        else:
                            # current
                            template['fulfillmentText'] = "{}{}的{}資訊如下：\n".format(period, place, task)
                            template['fulfillmentText'] += "目前濕度：{}％\n".format(ans['ans']['humidity'])
                    elif task == "風速":
                        if type(ans['ans']) == 'list':
                            # forcast
                            template['fulfillmentText'] = "{}{}的{}預報如下：\n".format(period, place, task)
                            if period == "週末":
                                for i, w in enumerate(ans['ans']):
                                    if i > 0:
                                        template['fulfillmentText'] += "\n"
                                    nextD = now +timedelta(days = i+(5 - now.timetuple()[6]))
                                    template['fulfillmentText'] += "{}月{}日（{}）\n".format(nextD.timetuple()[1], nextD.timetuple()[2],weekday[nextD.timetuple()[6]])
                                    template['fulfillmentText'] += "風速：{}公尺/秒\n".format(w['speed'])
                            elif period == "這週":
                                for i, w in enumerate(ans['ans']):
                                    if i > 0:
                                        template['fulfillmentText'] += "\n"
                                    nextD = now +timedelta(days = i+1)
                                    template['fulfillmentText'] += "{}月{}日（{}）\n".format(nextD.timetuple()[1], nextD.timetuple()[2],weekday[nextD.timetuple()[6]])
                                    template['fulfillmentText'] += "風速：{}公尺/秒\n".format(w['speed'])
                            else:
                                for i, w in enumerate(ans['ans']):
                                    if i > 0:
                                        template['fulfillmentText'] += "\n"
                                    template['fulfillmentText'] += "風速：{}公尺/秒\n".format(w['speed'])
                        else:
                            # current
                            template['fulfillmentText'] = "{}{}的{}資訊如下：\n".format(period, place, task)
                            template['fulfillmentText'] += "目前風速：{}公尺/秒\n".format(ans['ans']['wind'])
                else:
                    template['fulfillmentText'] = "很抱歉，我找不到\n{}\n的天氣資料，可能是有多個位置具有相同名稱，可以試試看用更精確的說法來查詢。"
        else:
            if 'source' in data['originalDetectIntentRequest'] and data['originalDetectIntentRequest']['source'] == "line" and data['originalDetectIntentRequest']['payload']['source']['type'] in ['room', 'group']:
                template['fulfillmentText'] = ""
            else:
                if 'fulfillmentText' in data['queryResult']:
                    template['fulfillmentText'] = data['queryResult']['fulfillmentText']
                else:
                    template['fulfillmentText'] = "偵測到的意圖是{}, 送來的訊息是{}".format(data['queryResult']['intent']['displayName'], data['queryResult']['queryText'])

        try:
            return jsonify(template)
        finally:
            try:
                del res
            except:
                pass
            sendtodb = ['python', 'linebotsql.py', str(rcv_timestamp), 'from_what', 'ask_timestamp', 'utype', 'uid', 'rq_msg', 'intent', 'rp_msg', str(timestamper())]
            if 'source' in data['originalDetectIntentRequest']: # from other integration
                sendtodb[3] = data['originalDetectIntentRequest']['source']
                sendtodb[4] = str(data['originalDetectIntentRequest']['payload']['timestamp'] / 1000)
                sendtodb[5] = data['originalDetectIntentRequest']['payload']['source']['type']
                sendtodb[6] = data['originalDetectIntentRequest']['payload']['source'][data['originalDetectIntentRequest']['payload']['source']['type']+'Id']
                sendtodb[7] = data['queryResult']['queryText']
                sendtodb[8] = data['queryResult']['intent']['displayName']
                sendtodb[9] = template['fulfillmentText']
            else: # from console
                sendtodb[3] = 'console'
                sendtodb[4] = ''
                sendtodb[5] = 'developer'
                sendtodb[6] = 'superuser'
                sendtodb[7] = data['queryResult']['queryText']
                sendtodb[8] = data['queryResult']['intent']['displayName']
                sendtodb[9] = template['fulfillmentText']

            if action_code == 1:
                sendtodb.append(data['queryResult']['parameters']['name'])
                sendtodb.append(("0" if data['queryResult']['parameters']['gender'] == '女' else "1" if data['queryResult']['parameters']['gender'] == '男' else "2"))
                sendtodb.append(data['queryResult']['parameters']['home'])

            if action_code == 2:
                '''
                    2006    # year [0]
                    11      # month [1]
                    21      # day [2]
                    16      # hour [3]
                    30      # minute [4]
                    0       # second [5]
                    1       # weekday (0 = Monday) [6]
                    325     # number of days since 1st January
                    -1      # dst - method tzinfo.dst() returned None
                '''
                sendtodb.append(rcv_dt.timetuple()[3])
                sendtodb.append(rcv_dt.timetuple()[6])
                sendtodb.append(task)
                sendtodb.append(period)
                sendtodb.append(place)
                sendtodb.append(geo['lat'])
                sendtodb.append(geo['lon'])

            if action_code == 3:
                sendtodb.append(rcv_dt.timetuple()[3])
                sendtodb.append(rcv_dt.timetuple()[6])
                sendtodb.append(place)
                sendtodb.append(geo['lat'])
                sendtodb.append(geo['lon'])

            sendtodb.append(str(action_code))
            print(sendtodb)

            for i_s2db, s2db in enumerate(sendtodb):
                sendtodb[i_s2db] = str(s2db)

            try:
                print(spcss.run(sendtodb))
            except spcss.CalledProcessError:
                print(spcss.CalledProcessError)
            except Exception as e:
                print(str(e))

            if datetime.now().timestamp() - LAST_UPDATE >= 86400:
                try:
                    print(spcss.run("python openplacetosql.py".split(" ")))
                except spcss.CalledProcessError:
                    print(spcss.CalledProcessError)
                except Exception as e:
                    print(str(e))
    else:
        return abort(401)


if __name__ == '__main__':
    app.debug = _DEBUGGING_
    app.run(host='0.0.0.0')
