#coding:utf-8
# mistick/proxy.rb 双色球数据代理 + 全量库
# CALL: ruby proxy.rb [port=8761]
# RETN: 常驻 127.0.0.1, 三端点:
#   GET /api/draws?count=N  最近 N 期(官方直转, 旧入口保留)
#   GET /api/sync           全量同步: 官方 2013+ 与 500网 2003-2012 合并写 draws.json
#   GET /api/all            读 draws.json 全量返回
# ☆ 福彩接口校验 Referer 且无 CORS 头, 浏览器直连必拦, 本代理补齐两头
# ☆ 官方接口 issueCount 上限即 2013001 起, 更早的从 500 网 history.php 补(GBK→UTF8 三层兜底)

require 'socket'
require 'net/http'
require 'uri'
require 'json'

PORT = (ARGV[0] || '8761').to_i
DB   = File.expand_path('draws.json', __dir__)    # 库文件紧邻脚本, 文件即数据库
UP   = URI('https://www.cwl.gov.cn/cwl_admin/front/cwlkj/search/kjxx/findDrawNotice')
W500 = URI('https://datachart.500.com/ssq/history/newinc/history.php?start=03001&end=12154')  # 区间参数, limit 语义不同勿混用
HDR  = {
  'Referer'    => 'https://www.cwl.gov.cn/ygkj/wqkjgg/ssq/',
  'User-Agent' => 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36',
}
H500 = {
  'Referer'    => 'https://datachart.500.com/ssq/',
  'User-Agent' => 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36',
}

#### 上游 ####
def http_get uri, hdr, limit = 30           #=> body 文本
  http = Net::HTTP.new(uri.host, uri.port)
  http.use_ssl = true
  http.open_timeout = 15
  http.read_timeout = limit
  uri.query ? http.get(uri.path + '?' + uri.query, hdr).body : http.get(uri.path, hdr).body
end

=begin
def pulls count                  # 旧入口函数, 已并入 pull_cwl, 隔离保留进化路径
  http_get(UP, HDR, 25)
rescue Exception => e
  %Q{{"state":-1,"message":"cwl upstream fail: #{e.class}"}}
end
=end

def pull_cwl                     #=> 官方全量数组 [{c,d,r,b,p,s}], 最新在前
  u = URI(UP.to_s + '?name=ssq&issueCount=99999')
  j = JSON.parse(http_get(u, HDR, 40))
  raise "state #{j['state']}" if j['state'] != 0
  j['result'].map do|x|
    { 'c' => x['code'], 'd' => x['date'].to_s.sub(/\(.*/, ''),
      'r' => x['red'],  'b' => x['blue'],
      'p' => x['poolmoney'].to_s.gsub(',', ''), 's' => x['sales'].to_s.gsub(',', '') }
  end
rescue Exception => e
  []
end

def 转 raw                     #=> GBK系转UTF8, 按合法校验逐层降级, 最终二进制保正则
  t = raw.force_encoding('GBK')
  return t.encode('UTF-8') if t.valid_encoding?
  t = raw.force_encoding('GB18030')
  return t.encode('UTF-8') if t.valid_encoding?
  raw.force_encoding('ASCII-8BIT')
end

def pull_500                     #=> 500网早期数组, 期号 5 位转 7 位
  raw = 转(http_get(W500, H500, 40))
  rows = raw.scan(/<td>(\d{5})<\/td>((?:<td class="t_cfont2">\d{2}<\/td>){6})<td class="t_cfont4">(\d{2})<\/td>.*?<td>(\d{4}-\d{2}-\d{2})<\/td>/m)
  rows.map do|code, reds, blue, date|
    { 'c' => '20' + code,                       # 03001 => 2003001
      'd' => date,
      'r' => reds.scan(/\d{2}/).join(','),
      'b' => blue, 'p' => nil, 's' => nil }
  end
rescue Exception => e
  []
end

#### 库 ####
def load_db                      #=> {t,count,draws} 或空骨架
  return { 't' => 0, 'count' => 0, 'draws' => [] } unless File.exist?(DB)
  JSON.parse(File.read(DB))
rescue Exception
  { 't' => 0, 'count' => 0, 'draws' => [] }
end

def save_db draws                #=> 排序去重写盘, 官方源优先(500网仅补缺)
  merged = {}
  draws.each { |d| merged[d['c']] = d unless merged[d['c']] }
  arr = merged.values.sort_by { |d| d['c'] }
  File.write(DB, JSON.generate({ 't' => Time.now.to_i, 'count' => arr.size, 'draws' => arr }))
  arr
end

def do_sync                      #=> {state,count,first,last,added}
  old = load_db['draws']
  fresh = pull_cwl
  early = pull_500.select { |d| d['c'] < '2013001' }
  arr = save_db(fresh + early + old)
  news = fresh.map { |d| d['c'] } - old.map { |d| d['c'] }
  if arr.empty?
    { 'state' => -1, 'message' => '双源均拉取失败, 检查网络' }
  else
    { 'state' => 0, 'count' => arr.size, 'first' => arr.first['c'], 'last' => arr.last['c'],
      'added' => news.size, 'cwl' => fresh.size, 'w500' => early.size }
  end
end

#### 服务 ####
server = TCPServer.new('127.0.0.1', PORT)
puts "mistick proxy listening 127.0.0.1:#{PORT}"
loop do
  c = server.accept
  Thread.new c do|cli|
    begin
      head = cli.gets.to_s
      cli.each { |l| l.strip.empty? and break }
      if head.include?('/api/sync')
        body = JSON.generate(do_sync); code = '200 OK'
      elsif head.include?('/api/all')
        body = JSON.generate(load_db); code = '200 OK'
      elsif head.include?('/api/draws')
        n = head[/count=(\d+)/, 1].to_i
        n = 30 if n < 1
        n = 100 if n > 100
        body = http_get(URI(UP.to_s + "?name=ssq&issueCount=#{n}"), HDR, 25)
        code = '200 OK'
      else
        body = %Q{{"state":-1,"message":"bad path, expect /api/draws /api/sync /api/all"}}
        code = '404 Not Found'
      end
      cli.print "HTTP/1.1 #{code}\r\n"
      cli.print "Content-Type: application/json; charset=utf-8\r\n"
      cli.print "Access-Control-Allow-Origin: *\r\n"
      cli.print "Content-Length: #{body.bytesize}\r\n"
      cli.print "Connection: close\r\n\r\n"
      cli.print body
    rescue Exception
    ensure
      cli.close rescue nil
    end
  end
end
