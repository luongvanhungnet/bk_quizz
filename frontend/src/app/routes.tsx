import { createBrowserRouter } from "react-router";
import { GuestOnly, RequireAdmin, RequireAuth } from "../auth/RouteGuards";
import { PageBrandLayout } from "./components/PageBrandLayout";
import Landing from "./pages/Landing";

export const router = createBrowserRouter([
  {
    Component: PageBrandLayout,
    children: [
      { path: "/", Component: Landing },
      {
        path: "/pricing",
        lazy: async () => ({
          Component: (await import("./pages/Pricing")).default,
        }),
      },
      {
        path: "/verify-email",
        lazy: async () => ({
          Component: (await import("./pages/VerifyEmail")).default,
        }),
      },
      {
        path: "/join-class/:joinCode",
        lazy: async () => ({
          Component: (await import("./pages/JoinClass")).default,
        }),
      },
      {
        Component: GuestOnly,
        children: [
          {
            path: "/login",
            lazy: async () => ({
              Component: (await import("./pages/Login")).default,
            }),
          },
          {
            path: "/register",
            lazy: async () => ({
              Component: (await import("./pages/Register")).default,
            }),
          },
          {
            path: "/forgot-password",
            lazy: async () => ({
              Component: (await import("./pages/ForgotPassword")).default,
            }),
          },
        ],
      },
      {
        Component: RequireAdmin,
        children: [
          {
            path: "/admin",
            lazy: async () => ({
              Component: (await import("./pages/Admin")).default,
            }),
          },
        ],
      },
      {
        Component: RequireAuth,
        children: [
          {
            path: "/dashboard",
            lazy: async () => ({
              Component: (await import("./pages/Dashboard")).default,
            }),
          },
          {
            path: "/topic/new",
            lazy: async () => ({
              Component: (await import("./pages/NewTopic")).default,
            }),
          },
          {
            path: "/workspace/:id",
            lazy: async () => ({
              Component: (await import("./pages/Workspace")).default,
            }),
          },
          {
            path: "/quiz/:id/take",
            lazy: async () => ({
              Component: (await import("./pages/QuizTaking")).default,
            }),
          },
          {
            path: "/attempt/:attemptId",
            lazy: async () => ({
              Component: (await import("./pages/QuizTaking")).default,
            }),
          },
          {
            path: "/classrooms",
            lazy: async () => ({
              Component: (await import("./pages/Classrooms")).default,
            }),
          },
          {
            path: "/classrooms/:classroomId",
            lazy: async () => ({
              Component: (await import("./pages/ClassroomDetail")).default,
            }),
          },
          {
            path: "/classrooms/:classroomId/resources/topics/:topicShareId",
            lazy: async () => ({
              Component: (await import("./pages/SharedClassroomResource"))
                .default,
            }),
          },
          {
            path: "/classrooms/:classroomId/resources/quizzes/:assignmentId",
            lazy: async () => ({
              Component: (await import("./pages/SharedClassroomResource"))
                .default,
            }),
          },
          {
            path: "/quizzes/:quizId/analytics",
            lazy: async () => ({
              Component: (await import("./pages/QuizAnalytics")).default,
            }),
          },
        ],
      },
    ],
  },
]);
