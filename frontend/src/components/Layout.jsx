import { Outlet } from "react-router-dom";
import { AppShell } from "../zip-design/AppShell";
import Footer from "./Footer";
export default function Layout() {
  return <AppShell><Outlet /><Footer /></AppShell>;
}
