function download(content, fileName, contentType) {
    var a = document.createElement("a");
    var file = new Blob([content], {type: contentType});
    a.href = URL.createObjectURL(file);
    a.download = fileName;
    a.click();
}
divs = document.querySelectorAll(".um-user-bookmarkss-list");
content = ""
for (i = 0; i < divs.length; i++) {
    a = divs[i].querySelector("a");
    content += a.href + "\n"
}
download(content, 'anitsu_bookmarks.txt', 'text/plain');
