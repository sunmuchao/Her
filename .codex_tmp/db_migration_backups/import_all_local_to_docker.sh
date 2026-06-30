#!/bin/sh
set -eu
TS=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/Users/sunmuchao/Downloads/Her/.codex_tmp/db_migration_backups/$TS"
mkdir -p "$BACKUP_DIR/docker_before" "$BACKUP_DIR/local_dumps"

docker run --rm --add-host host.docker.internal:host-gateway mysql:8.0 mysql -N -h host.docker.internal -P 3307 -uroot -e "SHOW DATABASES" | grep '^her' > "$BACKUP_DIR/local_databases.txt"

while IFS= read -r db; do
  if docker exec her-mysql-1 sh -lc "MYSQL_PWD=\$(cat /run/secrets/mysql_root_password) mysql -N -uroot -e \"SHOW DATABASES LIKE '$db'\"" | grep -qx "$db"; then
    docker exec her-mysql-1 sh -lc "MYSQL_PWD=\$(cat /run/secrets/mysql_root_password) mysqldump -uroot --single-transaction --routines --triggers --set-gtid-purged=OFF '$db'" > "$BACKUP_DIR/docker_before/$db.sql"
  fi
  docker run --rm --add-host host.docker.internal:host-gateway mysql:8.0 sh -lc "exec mysqldump -h host.docker.internal -P 3307 -uroot --single-transaction --routines --triggers --set-gtid-purged=OFF '$db'" > "$BACKUP_DIR/local_dumps/$db.sql"
done < "$BACKUP_DIR/local_databases.txt"

while IFS= read -r db; do
  docker exec her-mysql-1 sh -lc "MYSQL_PWD=\$(cat /run/secrets/mysql_root_password) mysql -uroot -e \"DROP DATABASE IF EXISTS \\`$db\\`; CREATE DATABASE \\`$db\\` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;\""
  docker exec -i her-mysql-1 sh -lc "MYSQL_PWD=\$(cat /run/secrets/mysql_root_password) mysql -uroot '$db'" < "$BACKUP_DIR/local_dumps/$db.sql"
done < "$BACKUP_DIR/local_databases.txt"

for db in her her_chat her_discovery her_matchmaking her_recommendation her_relationship_ledger her_state; do
  if grep -qx "$db" "$BACKUP_DIR/local_databases.txt"; then
    src_count=$(docker run --rm --add-host host.docker.internal:host-gateway mysql:8.0 mysql -N -h host.docker.internal -P 3307 -uroot -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='$db' AND table_type='BASE TABLE';")
    dst_count=$(docker exec her-mysql-1 sh -lc "MYSQL_PWD=\$(cat /run/secrets/mysql_root_password) mysql -N -uroot -e \"SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='$db' AND table_type='BASE TABLE';\"")
    echo "$db source_tables=$src_count docker_tables=$dst_count"
  fi
done

echo "BACKUP_DIR=$BACKUP_DIR"
