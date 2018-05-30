#coding=utf-8
import sys
import pymysql
# action_code = 0
# rcv_timestamp from_what ask_timestamp utype uid rq_msg intent rp_msg rp_time
# 0             1         2             3     4   5      6      7      8
#['1526993866', 'console', '',     'devo', 'sup', '1-3', 'playm', '(1): 1-3 = -2', '1526993866.5267725', '0']
#['1526993866', 'console', '', 'developer', 'superuser', '1-3', 'playmath', '(1): 1-3 = -2', '1526993866.5267725']

# action_code = 1
# rcv_timestamp from_what ask_timestamp utype uid rq_msg intent rp_msg rp_time u_name u_gender u_home
# 0             1         2             3     4   5      6      7      8       9      10       11

# action_code = 2
# rcv_timestamp from_what ask_timestamp utype uid rq_msg intent rp_msg rp_time `clock`, `weekday`, `task`, `period`, `place`, `geo_lat`, `geo_lon`
# 0             1         2             3     4   5      6      7      8       9        10         11       12        13       14         15

data = []
# argv[-1] = action control

if len(sys.argv) > 3:
    data = sys.argv[1:-1]

    db = pymysql.connect("localhost", "linebot", "linbotoffatcat", "linebot", port = 3307, use_unicode=True, charset="utf8")
    cursor = db.cursor()

    if sys.argv[-1] == "1":
        # recieve user given info
        sql0 = "INSERT INTO `users`(`register_time`, `u_id`, `u_type`, `plaform`, `gender`, `home`, `name`) VALUES ('{}', '{}', '{}', '{}', '{}', '{}', '{}')"
        sql = sql0.format(data[0], data[4], data[3], data[1], data[10], data[11], data[9])
        try:
            cursor.execute(sql)
            db.commit()
        except pymysql.err.IntegrityError:
            sql0 = "UPDATE `users` SET `gender`='{}',`home`='{}',`name`='{}' WHERE `u_id`='{}' AND `u_type`='{}' AND `plaform`='{}'"
            sql = sql0.format(data[10], data[11], data[9], data[4], data[3], data[1])
            try:
                cursor.execute(sql)
                db.commit()
            except Exception as e:
                db.rollback()
                with open("log.txt", 'a+') as f:
                    f.write(sql)
                    f.write('\n')
                    f.write(str(e))
                    f.write('\n')

        except Exception as e:
            db.rollback()
            with open("log.txt", 'a+') as f:
                f.write(sql)
                f.write('\n')
                f.write(str(e))
                f.write('\n')
    elif sys.argv[-1] == "2":
        # record weather_query history
        sql = "INSERT INTO `weatherQhistory`(`u_id`, `clock`, `weekday`, `task`, `period`, `place`, `geo_lat`, `geo_lon`) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)"
        try:
            cursor.execute(sql, (data[4], data[9], data[10], data[11], data[12], data[13], data[14], data[15]))
            db.commit()
        except Exception as e:
            db.rollback()
            with open("log.txt", 'a+') as f:
                f.write(sql)
                f.write('\n')
                f.write(str(e))
                f.write('\n\n\n')

    else:
        # record data to database
        sql1 = "INSERT INTO `users`(`register_time`, `u_id`, `u_type`, `plaform`) VALUES ('{}', '{}', '{}', '{}')"
        try:
            sql = sql1.format(data[0], data[4], data[3], data[1])
            cursor.execute(sql)
            db.commit()
        except pymysql.err.IntegrityError:
            pass
        except Exception as e:
            db.rollback()
            with open("log.txt", 'a+') as f:
                f.write(sql)
                f.write('\n')
                f.write(str(e))
                f.write('\n')

    sql2 = "INSERT INTO `history`(`ask_time`, `rcv_time`, `rp_time`, `u_id`, `u_platform`, `intent`, `rq_msg`, `rp_msg`) VALUES ('{0}', '{1}', '{2}', '{3}', '{4}', '{5}', '{6}', '{7}')"
    try:
        sql = sql2.format(data[2], data[0], data[8], data[4], data[1], data[6], data[5], data[7])
        cursor.execute(sql)
        db.commit()
    except Exception as e:
        db.rollback()
        with open("log.txt", 'a+') as f:
            f.write(sql)
            f.write('\n')
            f.write(str(e))
            f.write('\n')

    db.close()

exit(0)
