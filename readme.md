分析之前寫的程式
	./find_javdb_legend.py
	./copy_2_aj_ui.py
	./copy_2_aj_form.py

database:
	./my javdb.json : 所有影片的資料庫，不見得在庫
	./my collection.json : 已在庫的片單，及檔案path
	./maglink_added.json : 已在aria2下載過的magnet link
輸出新版的程式
	./jdb_download.py

將程式功能合併
1. 到https://javdb.com去搜尋新出的magnet links
   做成pyQT6 UI介面，參數跟原來的find_javdb_legend.py一樣，但改用UI輸入
page view
   1.1 由-il所指定的page開始、（沒指定就從default page https://javdb.com/censored 開始）每個page的每個album 進行暫停檢查，按了continue的button才繼續找下一個album
		ui 中也可以選擇，所有頁都要檢查、或是只檢查某一頁、或是可輸入一個範圍 （如3-5頁）
album view
   1.2 check 上市日期(在page view就有資訊，不用進到album view中來看） 決定是否是濾掉新片只看老片  或是不管新舊都要檢查 (-nl)
   1.3 album中的actors，是否是多位女性，是的話屬於Collection類， -nc則濾掉Collection，不檢查，否則就停下來檢查
   1.4 magnet中有沒有-c 中文片，或-u 的片子，或-uc, 二個情況擇一即可、就暫停進行檢查，並顯示album等待進一步決定
   1.5 或是check my collection.json看是否已有片子在庫了？在庫就略過、或是 -fda => 雖然在庫仍要再檢查下載一次


2. 當chrome在某一個album暫停，等待選擇magnet link時，如果有magnet link被copy到clipboard中
3. 檢查這個clipboard是
	3.1 pure magnet links
		check maglink_added.json 已下載過了不再下載，或是option=-fdm 仍要再次進aria2 server下載
		將它加入aria2的 download list,進行下載，並加到maglink_added.json中
    3.2 某一個album 的web link
		分析album的資料，將它加入my javdb.json存檔、資料格式與來源可參考原來的find_javdb_legend.py程式