import { lazy } from "react";

export const toolRegistry: Record<string, React.LazyExoticComponent<any>> = {
  "room-layout": lazy(() => import("./RoomLayoutTool")),
  "tower-layout": lazy(() => import("./TowerLayoutTool")),
  "parking-core": lazy(() => import("./ParkingCoreTool")),
};
