# MONGO
wget -qO - https://www.mongodb.org/static/pgp/server-4.4.asc | apt-key add -
apt-get install gnupg
wget -qO - https://www.mongodb.org/static/pgp/server-4.4.asc | apt-key add -

echo "deb [ arch=amd64,arm64 ] https://repo.mongodb.org/apt/ubuntu focal/mongodb-org/4.4 multiverse" | tee /etc/apt/sources.list.d/mongodb-org-4.4.list
apt-get update

systemctl start mongod

systemctl status mongod
systemctl enable mongod

# PYTHON 3.9
apt update
apt install software-properties-common

add-apt-repository ppa:deadsnakes/ppa

apt install python3.9
python3.9 --version


