import { useEffect, useRef } from "react";
import * as echarts from "echarts/core";
import { LineChart, BarChart } from "echarts/charts";
import { GridComponent, TooltipComponent, LegendComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";

echarts.use([LineChart, BarChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer]);

export function AdminChart({ title, labels, values, kind="line" }: {title:string;labels:string[];values:number[];kind?:"line"|"bar"}) {
  const ref=useRef<HTMLDivElement>(null);
  useEffect(()=>{
    if(!ref.current) return;
    const chart=echarts.init(ref.current);
    chart.setOption({title:{text:title,textStyle:{fontSize:14}},tooltip:{trigger:"axis"},grid:{left:45,right:15,top:45,bottom:35},
      xAxis:{type:"category",data:labels},yAxis:{type:"value"},series:[{type:kind,data:values,smooth:kind==="line",areaStyle:kind==="line"?{opacity:.08}:undefined}]});
    const resize=()=>chart.resize(); window.addEventListener("resize",resize);
    return()=>{window.removeEventListener("resize",resize);chart.dispose();};
  },[title,labels,values,kind]);
  return <div ref={ref} role="img" aria-label={title} className="h-72 w-full" />;
}
