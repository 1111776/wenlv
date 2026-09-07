import { useEffect, useMemo, useRef, useState } from "react";
import { Button, Space, Typography } from "antd";

const AMAP_KEY = "47459cb5c6b7974482121840bf5ff6f3";

// 每天的景点颜色（循环使用）
const DAY_COLORS = ["#1677ff", "#52c41a", "#fa8c16", "#722ed1", "#eb2f96", "#13c2c2", "#f5222d", "#a0d911"];

interface Spot {
  spot?: string;
  address?: string;
  location?: [number, number] | null;
  day?: number;
}

// 景点总览地图：展示全部行程景点，按天分组颜色 + 可切换只看某天
export default function MapView({ days }: { days: { day: number; spots: Spot[] }[] }) {
  const mapRef = useRef<HTMLDivElement>(null);
  const mapInstance = useRef<any>(null);
  const [selectedDay, setSelectedDay] = useState<number | "all">("all");

  // 稳定化依赖：序列化所有天的景点
  const spotsKey = useMemo(() => {
    return JSON.stringify(
      days.map((d) => ({
        day: d.day,
        spots: d.spots.map((s) => ({ name: s?.spot, loc: s?.location })),
      }))
    );
  }, [days]);

  // 有坐标的景点（全量）
  const validAll = useMemo(() => {
    const result: Spot[] = [];
    days.forEach((d) => {
      d.spots.forEach((s) => {
        if (Array.isArray(s.location) && s.location.length === 2 && s.location[0] && s.location[1]) {
          result.push({ ...s, day: d.day });
        }
      });
    });
    return result;
  }, [spotsKey]);

  // 当前展示的景点（按选择过滤）
  const shown = useMemo(() => {
    if (selectedDay === "all") return validAll;
    return validAll.filter((s) => s.day === selectedDay);
  }, [selectedDay, validAll]);

  useEffect(() => {
    if (!shown.length || !mapRef.current) return;

    const initMap = () => {
      const AMap = (window as any).AMap;
      if (!AMap || !mapRef.current) return;

      if (mapInstance.current) {
        try {
          mapInstance.current.destroy();
        } catch (e) {
          /* ignore */
        }
        mapInstance.current = null;
      }

      const map = new AMap.Map(mapRef.current, {
        zoom: 11,
        center: shown[0].location as [number, number],
        viewMode: "2D",
      });
      mapInstance.current = map;

      const markers: any[] = [];

      // 按天分组连线（同一天内的景点连线）
      const dayGroups: Record<number, Spot[]> = {};
      shown.forEach((s) => {
        if (!dayGroups[s.day!]) dayGroups[s.day!] = [];
        dayGroups[s.day!].push(s);
      });

      // 画每条天的路线（不同颜色）
      Object.values(dayGroups).forEach((group) => {
        if (group.length < 2) return;
        const color = DAY_COLORS[(group[0].day! - 1) % DAY_COLORS.length];
        const polyline = new AMap.Polyline({
          path: group.map((s) => s.location),
          strokeColor: color,
          strokeWeight: 4,
          strokeOpacity: 0.7,
          strokeStyle: "dashed",
        });
        polyline.setMap(map);
      });

      // 标记所有景点（编号全局连排）
      shown.forEach((s, i) => {
        const color = DAY_COLORS[(s.day! - 1) % DAY_COLORS.length];
        const marker = new AMap.Marker({
          position: s.location,
          title: s.spot,
          label: {
            content: `<div style="background:${color};color:#fff;border-radius:50%;width:22px;height:22px;line-height:22px;text-align:center;font-size:12px">${i + 1}</div>`,
            offset: new AMap.Pixel(0, -14),
          },
        });
        marker.setMap(map);
        markers.push(marker);

        const infoWindow = new AMap.InfoWindow({
          content: `<div style="padding:8px 10px;font-size:13px"><strong>${s.spot}</strong><br/>第 ${s.day} 天 · ${s.address || ""}</div>`,
          offset: new AMap.Pixel(0, -32),
        });
        marker.on("click", () => infoWindow.open(map, marker.getPosition()));
      });

      map.setFitView(markers);
    };

    const loadAMap = () => {
      if ((window as any).AMap) {
        initMap();
        return;
      }
      if (!(window as any).__amap_loading) {
        (window as any).__amap_loading = true;
        (window as any).__amap_cbs = [];
        const script = document.createElement("script");
        script.src = `https://webapi.amap.com/maps?v=2.0&key=${AMAP_KEY}&callback=__amap_ready`;
        (window as any).__amap_ready = () => {
          (window as any).__amap_loading = false;
          ((window as any).__amap_cbs || []).forEach((cb: any) => cb());
          (window as any).__amap_cbs = [];
        };
        script.onerror = () => {
          (window as any).__amap_loading = false;
          console.error("高德地图加载失败");
        };
        document.head.appendChild(script);
      }
      (window as any).__amap_cbs = (window as any).__amap_cbs || [];
      (window as any).__amap_cbs.push(initMap);
    };

    loadAMap();

    return () => {
      if (mapInstance.current && mapInstance.current.destroy) {
        try {
          mapInstance.current.destroy();
        } catch (e) {
          /* ignore */
        }
        mapInstance.current = null;
      }
    };
  }, [spotsKey, selectedDay]);

  if (validAll.length === 0) {
    return <Typography.Text type="secondary">暂无景点坐标信息</Typography.Text>;
  }

  return (
    <div>
      {/* 切换按钮 */}
      <Space style={{ marginBottom: 8 }} wrap>
        <Button
          size="small"
          type={selectedDay === "all" ? "primary" : "default"}
          onClick={() => setSelectedDay("all")}
        >
          全部
        </Button>
        {days.map((d) => (
          <Button
            key={d.day}
            size="small"
            type={selectedDay === d.day ? "primary" : "default"}
            onClick={() => setSelectedDay(d.day)}
          >
            第 {d.day} 天
          </Button>
        ))}
      </Space>
      <div ref={mapRef} style={{ width: "100%", height: 400, borderRadius: 8 }} />
      {/* 图例 */}
      <div style={{ marginTop: 8 }}>
        {days.map((d) => (
          <span key={d.day} style={{ marginRight: 16, fontSize: 12 }}>
            <span
              style={{
                display: "inline-block",
                width: 10,
                height: 10,
                borderRadius: "50%",
                background: DAY_COLORS[(d.day - 1) % DAY_COLORS.length],
                marginRight: 4,
              }}
            />
            第 {d.day} 天
          </span>
        ))}
      </div>
    </div>
  );
}
