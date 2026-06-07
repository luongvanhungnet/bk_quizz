import { createBrowserRouter } from "react-router";
import Landing from "./pages/Landing";
import Login from "./pages/Login";
import Register from "./pages/Register";
import ForgotPassword from "./pages/ForgotPassword";
import Dashboard from "./pages/Dashboard";
import NewTopic from "./pages/NewTopic";
import Workspace from "./pages/Workspace";
import QuizTaking from "./pages/QuizTaking";
import Pricing from "./pages/Pricing";

export const router = createBrowserRouter([
  { path: "/", Component: Landing },
  { path: "/pricing", Component: Pricing },
  { path: "/login", Component: Login },
  { path: "/register", Component: Register },
  { path: "/forgot-password", Component: ForgotPassword },
  { path: "/dashboard", Component: Dashboard },
  { path: "/topic/new", Component: NewTopic },
  { path: "/workspace/:id", Component: Workspace },
  { path: "/quiz/:id/take", Component: QuizTaking },
]);
