# anitsu_tools
[![test](https://github.com/b1337xyz/anitsu_tools/actions/workflows/flake8.yml/badge.svg)](https://github.com/b1337xyz/anitsu_tools/actions/workflows/flake8.yml)

## Dependências

- python
    - [requests](https://requests.readthedocs.io/en/latest/)
    - [aiohttp](https://github.com/aio-libs/aiohttp)
    - [aiofiles](https://github.com/Tinche/aiofiles)
    - [ueberzug](https://github.com/b1337xyz/ueberzug) (opcional) - exibe imagens (requer servidor gráfico)
- outros
    - [aria2](https://aria2.github.io/) - utilitário de download
    - [fzf](https://github.com/junegunn/fzf)
    - [imagemagick](https://github.com/ImageMagick/ImageMagick) - reduz o tamanho das imagens e converte para JPEG
    - [rclone](https://rclone.org) - suporte para Google Drive
    - [gdrive](https://github.com/prasmussen/gdrive) (opcional) - forma mais precisa para baixar arquivos do Google Drive
    - [viu](https://github.com/atanunq/viu#from-source-recommended) (opcional) - exibe imagens no terminal
    - [chafa](https://hpjansson.org/chafa/) (opcional) - idem `viu`

## Instalação

Arch Linux
```
sudo pacman -Syu python python-pip aria2 rclone fzf imagemagick ueberzug --needed
```

Debian
```
sudo apt install python3 python3-pip aria2 rclone fzf imagemagick ueberzug -y
```

<details>
    <summary>Crie um remote chamado Anitsu</summary>

Recomendado: [Criando seu próprio client_id](https://rclone.org/drive/#making-your-own-client-id)

```
rclone config
```

```
n) New remote
r) Rename remote
c) Copy remote
s) Set configuration password
q) Quit config
n/r/c/s/q> n
name> Anitsu
Type of storage to configure.
Choose a number from below, or type in your own value
[snip]
XX / Google Drive
   \ "drive"
[snip]
Storage> drive
Google Application Client Id - leave blank normally.
client_id>
Google Application Client Secret - leave blank normally.
client_secret>
Scope that rclone should use when requesting access from drive.
Choose a number from below, or type in your own value
 1 / Full access all files, excluding Application Data Folder.
   \ "drive"
 2 / Read-only access to file metadata and file contents.
   \ "drive.readonly"
   / Access to files created by rclone only.
 3 | These are visible in the drive website.
   | File authorization is revoked when the user deauthorizes the app.
   \ "drive.file"
   / Allows read and write access to the Application Data folder.
 4 | This is not visible in the drive website.
   \ "drive.appfolder"
   / Allows read-only access to file metadata but
 5 | does not allow any access to read or download file content.
   \ "drive.metadata.readonly"
scope> 1
Service Account Credentials JSON file path - needed only if you want use SA instead of interactive login.
service_account_file>
Remote config
Use web browser to automatically authenticate rclone with remote?
 * Say Y if the machine running rclone has a web browser you can use
 * Say N if running rclone on a (remote) machine without web browser access
If not sure try Y. If Y failed, try N.
y) Yes
n) No
y/n> y
If your browser doesn't open automatically go to the following link: http://127.0.0.1:53682/auth
Log in and authorize rclone for access
Waiting for code...
Got code
Configure this as a Shared Drive (Team Drive)?
y) Yes
n) No
y/n> n
--------------------
[remote]
client_id = 
client_secret = 
scope = drive
root_folder_id = 
service_account_file =
token = {"access_token":"XXX","token_type":"Bearer","refresh_token":"XXX","expiry":"2014-03-16T13:57:58.955387075Z"}
--------------------
y) Yes this is OK
e) Edit this remote
d) Delete this remote
y/e/d> y
```

</details>

```
git clone https://github.com/b1337xyz/anitsu_tools.git
cd anitsu_tools
python3 -m pip install -U --user -r requirements.txt
python3 anitsu-cli.py  # -i or --download-images to download images
```


## O que você pode fazer com isso...
![gif](assets/demo.gif)