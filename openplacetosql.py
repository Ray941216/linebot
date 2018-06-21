import sys
import pymysql
import requests as rqs
import pandas as pd
import numpy as np
from datetime import datetime
from time import time as timestamper


s = rqs.get("http://gis.taiwan.net.tw/XMLReleaseALL_public/scenic_spot_C_f.json")
res = s.json()

df = pd.DataFrame.from_records(data=res['XML_Head']['Infos']['Info'])
df = df.apply(lambda x: x.str.strip() if x.dtype == "object" else x).drop_duplicates().reset_index(drop=True)
for drop in ['Picture1', 'Picdescribe1', 'Level','Picture2', 'Id', 'Picdescribe2', 'Picture3', 'Picdescribe3', 'Map', 'Gov', 'Class2', 'Class3', 'Parkinginfo', 'Parkinginfo_Px', 'Parkinginfo_Py', 'Changetime', 'Zipcode', 'Zone']:
    try:
        discard = df.pop(drop)
    except:
        print("Error on", drop)
df = df.drop_duplicates()
df = df.reset_index(drop=True)

'''
'Add', 'Class1', 'Description', 'Keyword', 'Name',
'Opentime', 'Orgclass', 'Px', 'Py', 'Remarks',
'Tel', 'Ticketinfo', 'Toldescribe', 'Travellinginfo', 'Website'
'''

db = pymysql.connect("localhost", "linebot", "linbotoffatcat", "linebot", port = 3307, use_unicode=True, charset="utf8")
cursor = db.cursor()

sql= "INSERT INTO `place`(`addr`, `class`, `description`, `keyword`, `name`, `opentime`, `orgclass`, `lon`, `lat`, `remarks`, `tel`, `ticketinfo`, `toldescribe`, `travellinginfo`, `website`) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);"
data = []
for i, r in enumerate(df.values):
    data.append(tuple(r))
    if (i+1) % 500 == 0:
        try:
            cursor.executemany(sql, tuple(data))
            db.commit()
            print((i+1), ":done!")
        except Exception as e:
            db.rollback()
            for i_d, d in enumerate(data):
                try:
                    cursor.execute(sql, d)
                    db.commit()
                    print((i+1-500)+i_d,":done!")
                except pymysql.err.IntegrityError:
                    # print((i+1-500)+i_d,":pass!")
                    pass
                except Exception as e:
                    with open("logPlace.txt", 'a+') as f:
                        f.write('\n\n')
                        f.write(sql_base)
                        f.write('\n')
                        f.write("error:"+str(e))
                        f.write('\n')
        finally:
            data = []

try:
    cursor.executemany(sql, tuple(data))
    db.commit()
    print("ALL :done!")
except Exception as e:
    db.rollback()
    for i_d, d in enumerate(data):
        try:
            cursor.execute(sql, d)
            db.commit()
            print("fix", i_d,":done!")
        except pymysql.err.IntegrityError:
            print("fix", i_d,":pass!")
            pass
        except Exception as e:
            with open("logPlace.txt", 'a+') as f:
                f.write('\n\n')
                f.write(sql_base)
                f.write('\n')
                f.write("error:"+str(e))
                f.write('\n')
db.close()

exit(0)

"""

sql_base_del = "DELETE FROM `place`"
try:
    cursor.execute(sql_base_del)
    db.commit()
except Exception as e:
    db.rollback()
    with open("logPlace.txt", 'a+') as f:
        f.write('\n\n')
        f.write(sql_base)
        f.write('\n')
        f.write("error:"+str(e))
        f.write('\n')

"""
