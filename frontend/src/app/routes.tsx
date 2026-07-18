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
import VerifyEmail from "./pages/VerifyEmail";
import Classrooms from "./pages/Classrooms";
import ClassroomDetail from "./pages/ClassroomDetail";
import JoinClass from "./pages/JoinClass";
import QuizAnalytics from "./pages/QuizAnalytics";
import Admin from "./pages/Admin";
import { GuestOnly, RequireAdmin, RequireAuth } from "../auth/RouteGuards";

export const router = createBrowserRouter([
  { path: "/", Component: Landing },
  { path: "/pricing", Component: Pricing },
  { path: "/verify-email", Component: VerifyEmail },
  { path: "/join-class/:joinCode", Component: JoinClass },
  {
    Component: GuestOnly,
    children: [
      { path: "/login", Component: Login },
      { path: "/register", Component: Register },
      { path: "/forgot-password", Component: ForgotPassword },
    ],
  },
  {
    Component: RequireAdmin,
    children: [{ path: "/admin", Component: Admin }],
  },
  {
    Component: RequireAuth,
    children: [
      { path: "/dashboard", Component: Dashboard },
      { path: "/topic/new", Component: NewTopic },
      { path: "/workspace/:id", Component: Workspace },
      { path: "/quiz/:id/take", Component: QuizTaking },
      { path: "/attempt/:attemptId", Component: QuizTaking },
      { path: "/classrooms", Component: Classrooms },
      { path: "/classrooms/:classroomId", Component: ClassroomDetail },
      { path: "/quizzes/:quizId/analytics", Component: QuizAnalytics },
    ],
  },
]);
