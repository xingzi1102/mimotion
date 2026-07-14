#!/bin/bash

# 辅助函数：将 UTC cron 小时转为北京时间（仅用于日志）
function convert_utc_to_shanghai {
  local cron_str=$1
  echo "UTC时间: ${cron_str}"
  minute=$(echo "$cron_str" | awk '{print $1}')
  hours=$(echo "$cron_str" | awk '{print $2}')
  lines=$(echo "$hours"|awk -F ',' '{for (i=1;i<=NF;i++) { print ($i+8)%24 }}')
  result=""
  while IFS= read -r line; do
    if [ -z "$result" ]; then
      result="$line"
    else
      result="$result,$line"
    fi
  done <<< "$lines"
  echo "北京时间: $minute $result * * *'"
}

# 核心函数：随机化所有 cron 行的分钟，保留其余部分
function persist_execute_log {
  local event_name=$1
  # 忽略第二个参数（原 CRON_HOURS）

  # 写入日志文件
  echo "trigger by: ${event_name}" > cron_change_time
  {
    echo "current system time:"
    TZ='UTC' date "+%y-%m-%d %H:%M:%S" | xargs -I {} echo "UTC: {}"
    TZ='Asia/Shanghai' date "+%y-%m-%d %H:%M:%S" | xargs -I {} echo "北京时间: {}"
  } >> cron_change_time

  # 记录当前 cron（示例取第一行）
  current_cron=$(< .github/workflows/run.yml grep cron | head -1 | awk '{print substr($0, index($0,$3))}')
  {
    echo "current cron (sample):"
    convert_utc_to_shanghai "$current_cron"
  } >> cron_change_time

  # 生成随机分钟（0~59）
  RANDOM_MIN=$((RANDOM % 60))

  # 根据操作系统选择 sed 参数
  os=$(uname -s)
  sed_prefix=(sed -i)
  if [[ $os == "Darwin" ]]; then
    sed_prefix=(sed -i '')
  fi

  # 替换所有 cron 行的分钟数字，保留后面的全部内容（小时、日期、星期等）
  "${sed_prefix[@]}" -E "s/(- cron: ')[0-9]+( .*')/\1$RANDOM_MIN\2/g" .github/workflows/run.yml

  # 记录新的 cron（示例取第一行）
  new_cron=$(< .github/workflows/run.yml grep cron | head -1 | awk '{print substr($0, index($0,$3))}')
  {
    echo "next cron (sample):"
    convert_utc_to_shanghai "$new_cron"
    echo "所有 cron 行的分钟已统一随机为 $RANDOM_MIN"
  } >> cron_change_time
}