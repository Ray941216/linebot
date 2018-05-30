import sys
import pymysql
import json

db = pymysql.connect("localhost", "linebot", "linbotoffatcat", "linebot", port = 3307, use_unicode=True, charset="utf8")
cursor = db.cursor()

city = []
with open("./city_list.txt", 'rb') as f:
     lines = [l.decode('utf8', 'ignore') for l in f.readlines()]

for i, l in enumerate(lines):
    if i > 0:
        if l != "":
            s = l.split("\t")
            city.append({
                'id': s[0],
                'lat': float(s[2]),
                'lon': float(s[3])
            })
        else:
            break

print("Total:", len(city))
sql = ""
for i, ct in enumerate(city):
    sql = "INSERT INTO `city`(`id`, `lat`, `lon`) VALUES (%s, %s, %s);"
    try:
        cursor.execute(sql, (ct['id'], ct['lat'], ct['lon']))
        db.commit()
        print(i + 1, ": done!")
    except pymysql.err.IntegrityError:
        print(i + 1, ":pass!")
        pass
    except Exception as e:
        print(ct, " :error!")
        db.rollback()
        with open("logcity2.txt", 'a+') as f:
            f.write(sql)
            f.write('\n')
            f.write(str(e))
            f.write('\n')





with open("./city.list.json", 'r') as f:
    city = json.load(f)

print("Total:", len(city))
for i, ct in enumerate(city):
    try:
        sql = "INSERT INTO `city`(`id`, `lat`, `lon`) VALUES (%s, %s, %s);"
        cursor.execute(sql, (ct['id'], ct['coord']['lat'], ct['coord']['lon']))
        db.commit()
        print(i + 1, ": done!")
    except pymysql.err.IntegrityError:
        print(i + 1, ":pass!")
        pass
    except Exception as e:
        print(ct, " :error!")
        db.rollback()
        with open("logcity.txt", 'a+') as f:
            f.write(sql)
            f.write('\n')
            f.write(str(e))
            f.write('\n')

db.close()
