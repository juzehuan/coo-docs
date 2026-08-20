(function () {
  var style = getComputedStyle(document.documentElement);
  var accent = style.getPropertyValue('--accent').trim();
  var accent2 = style.getPropertyValue('--accent2').trim();
  var ink = style.getPropertyValue('--ink').trim();
  var muted = style.getPropertyValue('--muted').trim();
  var rule = style.getPropertyValue('--rule').trim();
  var bg2 = style.getPropertyValue('--bg2').trim();

  var el = document.getElementById('chart-effort');
  if (!el) return;

  var chart = echarts.init(el, null, { renderer: 'svg' });
  chart.setOption({
    animation: false,
    tooltip: {
      trigger: 'axis',
      appendToBody: true,
      axisPointer: { type: 'shadow' },
      formatter: function (params) {
        var p = params[0];
        return p.name + '<br/>周期：<b>' + p.value + '</b> 周';
      }
    },
    grid: { left: 48, right: 24, top: 24, bottom: 40 },
    xAxis: {
      type: 'category',
      data: ['① 后端+数据库', '② 前端重建', '③ NAS+部署', '④ 试点上线'],
      axisLine: { lineStyle: { color: rule } },
      axisLabel: { color: ink, fontSize: 13 }
    },
    yAxis: {
      type: 'value',
      name: '周',
      nameTextStyle: { color: muted },
      axisLabel: { color: muted },
      splitLine: { lineStyle: { color: rule } }
    },
    series: [{
      type: 'bar',
      data: [3, 3, 1, 2],
      barWidth: 48,
      itemStyle: {
        borderRadius: [6, 6, 0, 0],
        color: function (params) {
          return params.dataIndex === 2 ? accent + '88' : accent;
        }
      },
      label: {
        show: true,
        position: 'top',
        color: ink,
        fontSize: 13,
        fontWeight: 600,
        formatter: '{c} 周'
      }
    }]
  });
  window.addEventListener('resize', function () { chart.resize(); });
})();
