import { apiClient } from "./runtime";
import type { PaginatedResult } from "./client";
import type { UserDto } from "../auth/types";
import type { AuthPayload } from "../auth/types";
import { accessTokenStore } from "../auth/accessToken";

export type Visibility = "PRIVATE" | "PUBLIC";
export type TopicStatus = "DRAFT" | "PUBLISHED" | "ARCHIVED";
export type QuizStatus =
  | "DRAFT"
  | "QUEUED"
  | "GENERATING"
  | "READY"
  | "FAILED"
  | "PUBLISHED"
  | "ARCHIVED";
export type Difficulty = "EASY" | "MEDIUM" | "HARD" | "MIXED";
export type QuestionType = "SINGLE_CHOICE" | "MULTIPLE_SELECT" | "FILL_BLANK";

export interface Topic {
  id: string;
  ownerId: string;
  title: string;
  description: string | null;
  visibility: Visibility;
  status: TopicStatus;
  publishedAt: string | null;
  createdAt: string;
  updatedAt: string;
  version: number;
}
export interface Quiz {
  id: string;
  topicId: string;
  ownerId: string;
  title: string;
  description: string | null;
  status: QuizStatus;
  visibility: Visibility;
  generationMode: "MANUAL" | "AI";
  difficulty: Difficulty;
  durationMinutes: number;
  questionCount: number;
  errorCode: string | null;
  errorMessage: string | null;
  publishedAt: string | null;
  createdAt: string;
  updatedAt: string;
  version: number;
}
export interface Source {
  id: string;
  topicId: string;
  name: string;
  kind: string;
  status:
    | "UPLOADED"
    | "SCANNING"
    | "EXTRACTING"
    | "EMBEDDING"
    | "READY"
    | "FAILED"
    | "DELETED";
  contentType: string | null;
  sizeBytes: number | null;
  errorCode: string | null;
  errorMessage: string | null;
  indexingProgress: number;
  indexingStep: string | null;
  processingStage: string;
  processingDelayed: boolean;
  processorAvailable: boolean;
  indexingProgressAt: string;
  pageCount: number | null;
  chunkCount: number;
  indexedAt: string | null;
  createdAt: string;
  updatedAt: string;
  version: number;
}
export interface Job {
  id: string;
  type: string;
  status: "QUEUED" | "RUNNING" | "RETRY" | "SUCCEEDED" | "FAILED";
  resourceId: string;
  attempts: number;
  maxAttempts: number;
  progress: number;
  step: string | null;
  errorCode: string | null;
  errorMessage: string | null;
  upstreamRequestId: string | null;
  availableAt: string | null;
}
export interface QuestionOption {
  id: string;
  text: string;
  correct: boolean;
  position: number;
}
export interface Question {
  id: string;
  quizId: string;
  type: QuestionType;
  prompt: string;
  explanation: string | null;
  points: number;
  position: number;
  difficulty: Difficulty;
  options: QuestionOption[];
  acceptedAnswers: string[];
  citations: Citation[];
  version: number;
}
export interface Citation {
  sourceChunkId: string;
  sourceDocumentId: string;
  filename: string;
  pageNumber: number | null;
  slideNumber: number | null;
  chunkIndex: number;
  heading: string | null;
  role: "QUESTION" | "ANSWER" | "EXPLANATION";
  evidenceQuote: string;
}
export interface PublicQuiz {
  id: string;
  title: string;
  difficulty: Difficulty;
  durationMinutes: number;
  questionCount: number;
  publishedAt: string;
}
export interface PublicTopic {
  id: string;
  title: string;
  description: string | null;
  ownerId: string;
  ownerUsername: string;
  quizCount: number;
  learnerCount: number;
  bookmarkCount: number;
  publishedAt: string;
}
export interface PublicTopicDetail {
  topic: PublicTopic;
  quizzes: PublicQuiz[];
}
export interface SavedTopic {
  topic: PublicTopic;
  savedAt: string;
}
export interface Preferences {
  emailStudyReminders: boolean;
  publicProfile: boolean;
  attemptAutosave: boolean;
}
export interface DashboardData {
  stats: {
    topicCount: number;
    quizCount: number;
    submittedAttemptCount: number;
    averagePercentage: number;
  };
  recentTopics: Array<{
    id: string;
    title: string;
    description: string | null;
    visibility: Visibility;
    status: TopicStatus;
    updatedAt: string;
  }>;
  recentActivities: Array<{
    attemptId: string;
    quizId: string;
    quizTitle: string;
    status: string;
    percentage: number | null;
    occurredAt: string;
  }>;
}
export interface AttemptQuestion {
  snapshotId: string;
  type: QuestionType;
  prompt: string;
  points: number;
  position: number;
  options: Array<{ id: string; text: string; position: number }>;
}
export interface SavedAnswer {
  snapshotId: string;
  selectedOptionIds: string[];
  textAnswer: string | null;
  version: number;
  answeredAt: string;
  confirmedAt: string | null;
}
export interface AnswerFeedback {
  snapshotId: string;
  correct: boolean;
  awardedPoints: number;
  maxPoints: number;
  correctOptionIds: string[];
  acceptedAnswers: string[];
  explanation: string | null;
  citations: Citation[];
  confirmedAt: string;
}
export interface Attempt {
  id: string;
  quizId: string;
  assignmentId: string | null;
  status: string;
  startedAt: string;
  expiresAt: string;
  submittedAt: string | null;
  mode: "STANDARD" | "LIVE_FEEDBACK";
  version: number;
  questions: AttemptQuestion[];
  answers: SavedAnswer[];
  confirmedFeedback: AnswerFeedback[];
}
export interface AttemptResult {
  attemptId: string;
  quizId: string;
  status: string;
  score: number | null;
  maxScore: number | null;
  percentage: number | null;
  timedOut: boolean;
  answersReleased: boolean;
  submittedAt: string;
  questions: Array<{
    snapshotId: string;
    correct: boolean | null;
    awardedPoints: number;
    maxPoints: number;
    correctOptionIds: string[] | null;
    acceptedAnswers: string[] | null;
    explanation: string | null;
    citations: Citation[];
  }>;
}

export interface Classroom {
  id: string;
  ownerId: string;
  name: string;
  description: string | null;
  joinCode: string;
  joinEnabled: boolean;
  status: "ACTIVE" | "ARCHIVED";
  createdAt: string;
  updatedAt: string;
}
export interface ClassroomPreview {
  classroomId: string;
  name: string;
  ownerUsername: string;
  memberCount: number;
  joinEnabled: boolean;
}
export interface ClassroomMember {
  id: string;
  userId: string;
  username: string;
  role: "OWNER" | "TEACHER" | "STUDENT";
  status: string;
  joinedAt: string;
}
export interface ClassroomAttachment {
  id: string;
  name: string;
  mediaType: string;
  sizeBytes: number;
  image: boolean;
  accessUrl: string | null;
}
export interface SharedResourcePreview {
  kind: "TOPIC" | "QUIZ";
  resourceId: string | null;
  referenceId: string | null;
  title: string;
  description: string | null;
  ownerUsername: string | null;
  available: boolean;
  unavailableReason: string | null;
  quizCount: number;
  questionCount: number;
  difficulty: Difficulty | null;
  durationMinutes: number | null;
  assignmentStatus: "DRAFT" | "PUBLISHED" | "CLOSED" | null;
  opensAt: string | null;
  dueAt: string | null;
  maxAttempts: number | null;
}
export interface ClassroomMessage {
  id: string;
  classroomId: string;
  senderId: string;
  senderUsername: string;
  type: "TEXT" | "IMAGE" | "FILE" | "TOPIC_SHARE" | "QUIZ_SHARE" | "SYSTEM";
  content: string | null;
  topicShareId: string | null;
  assignmentId: string | null;
  resourcePreview: SharedResourcePreview | null;
  attachments: ClassroomAttachment[];
  editedAt: string | null;
  deletedAt: string | null;
  createdAt: string;
  version: number;
}
export interface SharedTopicDetail {
  preview: SharedResourcePreview;
  topic: Topic;
  quizzes: Quiz[];
}
export interface SharedQuizDetail {
  preview: SharedResourcePreview;
  quiz: Quiz;
  assignment: Assignment;
}
export interface ClassroomMessagesPage {
  items: ClassroomMessage[];
  nextBefore: string | null;
  nextBeforeId: string | null;
  unreadCount: number;
}
export interface TopicShare {
  id: string;
  classroomId: string;
  topicId: string;
  sharedBy: string;
  createdAt: string;
  resourcePreview: SharedResourcePreview;
}
export interface Assignment {
  id: string;
  classroomId: string;
  quizId: string;
  createdBy: string;
  title: string;
  instructions: string | null;
  status: "DRAFT" | "PUBLISHED" | "CLOSED";
  opensAt: string | null;
  dueAt: string | null;
  durationMinutes: number;
  maxAttempts: number;
  answerReleasePolicy: "IMMEDIATE" | "AFTER_DUE_DATE" | "NEVER";
  shareKind: "TEACHER_ASSIGNMENT" | "MEMBER_SHARE";
  showScore: boolean;
  allowReview: boolean;
  shuffleQuestions: boolean;
  shuffleOptions: boolean;
  showLeaderboard: boolean;
}
export interface AssignmentSubmission {
  attemptId: string;
  userId: string;
  username: string;
  status: string;
  attemptNumber: number;
  score: number | null;
  maxScore: number | null;
  percentage: number | null;
  timedOut: boolean;
  startedAt: string;
  submittedAt: string | null;
}
export interface QuizAnalyticsSummary {
  participantCount: number;
  attemptCount: number;
  completedCount: number;
  averagePercentage: number;
  highestPercentage: number;
  lowestPercentage: number;
  averageDurationSeconds: number;
}
export interface QuizAnalyticsParticipant {
  attemptId: string;
  userId: string;
  username: string;
  attemptNumber: number;
  score: number;
  maxScore: number;
  percentage: number;
  durationSeconds: number;
  submittedAt: string;
}
export interface QuizAnalyticsQuestion {
  questionId: string;
  prompt: string;
  answerCount: number;
  correctCount: number;
  correctRate: number;
}

const json = (body: unknown): RequestInit => ({
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});
const pageQuery = (
  path: string,
  params: Record<string, string | number | undefined>,
) =>
  `${path}?${new URLSearchParams(
    Object.entries(params)
      .filter(([, value]) => value !== undefined)
      .map(([key, value]) => [key, String(value)]),
  )}`;
const requestPage = <T>(path: string) => {
  if (!apiClient.requestPage)
    throw new Error("API client chưa hỗ trợ phân trang.");
  return apiClient.requestPage<T>(path);
};

export const bkquizApi = {
  topics: (page = 1, size = 100) =>
    requestPage<Topic>(
      pageQuery("/topics", { page: page - 1, size, sort: "updatedAt,desc" }),
    ),
  topic: (id: string) => apiClient.request<Topic>(`/topics/${id}`),
  createTopic: (body: {
    title: string;
    description?: string;
    visibility: Visibility;
  }) => apiClient.request<Topic>("/topics", { method: "POST", ...json(body) }),
  updateTopic: (
    id: string,
    body: { title: string; description?: string; visibility: Visibility },
  ) =>
    apiClient.request<Topic>(`/topics/${id}`, { method: "PUT", ...json(body) }),
  publishTopic: (id: string) =>
    apiClient.request<Topic>(`/topics/${id}/publish`, { method: "POST" }),
  deleteTopic: (id: string) =>
    apiClient.request<void>(`/topics/${id}`, { method: "DELETE" }),
  explore: (q = "", sort = "recent", page = 1) =>
    requestPage<PublicTopic>(
      pageQuery("/explore/topics", { q, sort, page, limit: 20 }),
    ),
  exploreTopic: (id: string) =>
    apiClient.request<PublicTopicDetail>(`/explore/topics/${id}`),
  savedTopics: (page = 1) =>
    requestPage<SavedTopic>(pageQuery("/topic-bookmarks", { page, limit: 20 })),
  saveTopic: (id: string) =>
    apiClient.request<SavedTopic>(`/topics/${id}/bookmark`, { method: "PUT" }),
  unsaveTopic: (id: string) =>
    apiClient.request<void>(`/topics/${id}/bookmark`, { method: "DELETE" }),
  profile: () => apiClient.request<UserDto>("/users/me/profile"),
  updateProfile: (body: {
    username: string;
    bio?: string;
  }) =>
    apiClient.request<UserDto>("/users/me/profile", {
      method: "PUT",
      ...json(body),
    }),
  uploadAvatar: (file: File) => {
    const body = new FormData();
    body.append("file", file);
    return apiClient.request<UserDto>("/users/me/avatar", { method: "POST", body });
  },
  deleteAvatar: () => apiClient.request<UserDto>("/users/me/avatar", { method: "DELETE" }),
  changeAccountType: async (targetRole: "STUDENT" | "TEACHER", password: string) => {
    const payload = await apiClient.request<AuthPayload>("/users/me/account-type", {
      method: "POST",
      ...json({ targetRole, password }),
    });
    accessTokenStore.set(payload.accessToken);
    return payload;
  },
  preferences: () => apiClient.request<Preferences>("/users/me/preferences"),
  updatePreferences: (body: Partial<Preferences>) =>
    apiClient.request<Preferences>("/users/me/preferences", {
      method: "PUT",
      ...json(body),
    }),
  dashboard: () => apiClient.request<DashboardData>("/users/me/dashboard"),
  requestDeletion: (password: string) =>
    apiClient.request<void>("/users/me/deletion-request", {
      method: "POST",
      ...json({ password }),
    }),
  sources: (topicId: string) =>
    apiClient.request<Source[]>(`/topics/${topicId}/sources`),
  pasteSource: (topicId: string, name: string, text: string) =>
    apiClient.request<Source>(`/topics/${topicId}/sources/text`, {
      method: "POST",
      ...json({ name, text }),
    }),
  uploadSource: async (topicId: string, file: File) => {
    const body = new FormData();
    body.append("file", file);
    return apiClient.request<{ source: Source; jobId: string }>(
      `/topics/${topicId}/sources/upload`,
      {
        method: "POST",
        body,
        headers: { "Idempotency-Key": crypto.randomUUID() },
      },
    );
  },
  deleteSource: (id: string) =>
    apiClient.request<void>(`/sources/${id}`, { method: "DELETE" }),
  reindexSource: (id: string) =>
    apiClient.request<{ source: Source; jobId: string }>(`/sources/${id}/reindex`, { method: "POST" }),
  job: (id: string) => apiClient.request<Job>(`/jobs/${id}`),
  quizzes: (topicId: string) =>
    requestPage<Quiz>(
      pageQuery("/quizzes", {
        topicId,
        page: 0,
        size: 100,
        sort: "updatedAt,desc",
      }),
    ),
  quiz: (id: string) => apiClient.request<Quiz>(`/quizzes/${id}`),
  quizSources: (id: string) => apiClient.request<Source[]>(`/quizzes/${id}/sources`),
  createQuiz: (body: {
    topicId: string;
    title: string;
    description?: string;
    difficulty: Difficulty;
    durationMinutes: number;
    visibility: Visibility;
  }) => apiClient.request<Quiz>("/quizzes", { method: "POST", ...json(body) }),
  generateQuiz: (body: {
    topicId: string;
    sourceIds: string[];
    title: string;
    difficulty: Difficulty;
    durationMinutes: number;
    visibility: Visibility;
    questionCounts: {
      singleChoice: number;
      multipleSelect: number;
      fillBlank: number;
    };
  }) =>
    apiClient.request<{ quiz: Quiz; jobId: string }>("/quizzes/generate", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": crypto.randomUUID(),
      },
      body: JSON.stringify(body),
    }),
  retryLastQuizGeneration: (quizId: string) =>
    apiClient.request<{ quiz: Quiz; jobId: string }>(
      `/quizzes/${quizId}/generation/retry-last`,
      {
        method: "POST",
        headers: { "Idempotency-Key": crypto.randomUUID() },
      },
    ),
  publishQuiz: (id: string) =>
    apiClient.request<Quiz>(`/quizzes/${id}/publish`, { method: "POST" }),
  deleteQuiz: (id: string) =>
    apiClient.request<void>(`/quizzes/${id}`, { method: "DELETE" }),
  questions: (quizId: string) =>
    apiClient.request<Question[]>(`/quizzes/${quizId}/questions`),
  createQuestion: (quizId: string, body: unknown) =>
    apiClient.request<Question>(`/quizzes/${quizId}/questions`, {
      method: "POST",
      ...json(body),
    }),
  deleteQuestion: (id: string) =>
    apiClient.request<void>(`/questions/${id}`, { method: "DELETE" }),
  startAttempt: (
    quizId: string,
    assignmentId?: string,
    mode: "STANDARD" | "LIVE_FEEDBACK" = "STANDARD",
  ) =>
    apiClient.request<Attempt>(`/quizzes/${quizId}/attempts`, {
      method: "POST",
      ...json({ ...(assignmentId ? { assignmentId } : {}), mode }),
    }),
  attempt: (id: string) => apiClient.request<Attempt>(`/attempts/${id}`),
  autosave: (
    id: string,
    attemptVersion: number,
    answers: Array<{
      snapshotId: string;
      selectedOptionIds: string[];
      textAnswer?: string;
    }>,
  ) =>
    apiClient.request<Attempt>(`/attempts/${id}/answers`, {
      method: "PUT",
      ...json({ attemptVersion, answers }),
    }),
  confirmAnswer: (
    attemptId: string,
    snapshotId: string,
    attemptVersion: number,
    answer: { selectedOptionIds: string[]; textAnswer?: string },
  ) =>
    apiClient.request<AnswerFeedback>(
      `/attempts/${attemptId}/answers/${snapshotId}/confirm`,
      {
        method: "POST",
        ...json({ attemptVersion, ...answer }),
      },
    ),
  submit: (id: string, key: string) =>
    apiClient.request<AttemptResult>(`/attempts/${id}/submit`, {
      method: "POST",
      headers: { "Idempotency-Key": key },
    }),
  result: (id: string) =>
    apiClient.request<AttemptResult>(`/attempts/${id}/result`),
  classrooms: (page = 1) =>
    requestPage<Classroom>(pageQuery("/classrooms", { page, limit: 50 })),
  classroom: (id: string) => apiClient.request<Classroom>(`/classrooms/${id}`),
  createClassroom: (body: { name: string; description?: string }) =>
    apiClient.request<Classroom>("/classrooms", {
      method: "POST",
      ...json(body),
    }),
  classroomPreview: (code: string) =>
    apiClient.request<ClassroomPreview>(
      `/classrooms/join/${encodeURIComponent(code)}/preview`,
    ),
  joinClassroom: (joinCode: string) =>
    apiClient.request<Classroom>("/classrooms/join", {
      method: "POST",
      ...json({ joinCode }),
    }),
  classroomMembers: (id: string) =>
    apiClient.request<ClassroomMember[]>(`/classrooms/${id}/members`),
  removeClassroomMember: (id: string, userId: string) =>
    apiClient.request<void>(`/classrooms/${id}/members/${userId}`, {
      method: "DELETE",
    }),
  leaveClassroom: (id: string) =>
    apiClient.request<void>(`/classrooms/${id}/leave`, { method: "POST" }),
  classroomMessages: (id: string, before?: string, beforeId?: string) =>
    apiClient.request<ClassroomMessagesPage>(
      pageQuery(`/classrooms/${id}/messages`, { before, beforeId, limit: 50 }),
    ),
  sendClassroomMessage: (
    id: string,
    body: { content?: string; attachmentIds?: string[] },
  ) =>
    apiClient.request<ClassroomMessage>(`/classrooms/${id}/messages`, {
      method: "POST",
      ...json(body),
    }),
  editClassroomMessage: (
    classroomId: string,
    messageId: string,
    content: string,
  ) =>
    apiClient.request<ClassroomMessage>(
      `/classrooms/${classroomId}/messages/${messageId}`,
      { method: "PATCH", ...json({ content }) },
    ),
  deleteClassroomMessage: (classroomId: string, messageId: string) =>
    apiClient.request<void>(
      `/classrooms/${classroomId}/messages/${messageId}`,
      { method: "DELETE" },
    ),
  markClassroomRead: (id: string) =>
    apiClient.request<void>(`/classrooms/${id}/messages/read`, {
      method: "POST",
    }),
  uploadClassroomAttachment: (id: string, file: File) => {
    const body = new FormData();
    body.append("file", file);
    return apiClient.request<ClassroomAttachment>(
      `/classrooms/${id}/attachments`,
      { method: "POST", body },
    );
  },
  classroomAttachmentAccess: (classroomId: string, attachmentId: string) =>
    apiClient.request<{ url: string; expiresAt: string }>(
      `/classrooms/${classroomId}/attachments/${attachmentId}/access`,
    ),
  classroomTopicShares: (id: string) =>
    apiClient.request<TopicShare[]>(`/classrooms/${id}/topic-shares`),
  shareTopic: (id: string, topicId: string, message?: string) =>
    apiClient.request<TopicShare>(`/classrooms/${id}/topic-shares`, {
      method: "POST",
      ...json({ topicId, message }),
    }),
  revokeTopicShare: (id: string, shareId: string) =>
    apiClient.request<void>(`/classrooms/${id}/topic-shares/${shareId}`, {
      method: "DELETE",
    }),
  sharedTopic: (classroomId: string, shareId: string) =>
    apiClient.request<SharedTopicDetail>(
      `/classrooms/${classroomId}/shared-resources/topics/${shareId}`,
    ),
  sharedQuiz: (classroomId: string, assignmentId: string) =>
    apiClient.request<SharedQuizDetail>(
      `/classrooms/${classroomId}/shared-resources/quizzes/${assignmentId}`,
    ),
  assignments: (id: string, page = 1) =>
    requestPage<Assignment>(
      pageQuery(`/classrooms/${id}/assignments`, { page, limit: 50 }),
    ),
  createAssignment: (
    id: string,
    body: Omit<
      Assignment,
      "id" | "classroomId" | "createdBy" | "status" | "shareKind"
    >,
  ) =>
    apiClient.request<Assignment>(`/classrooms/${id}/assignments`, {
      method: "POST",
      ...json(body),
    }),
  publishAssignment: (id: string) =>
    apiClient.request<Assignment>(`/assignments/${id}/publish`, {
      method: "POST",
    }),
  assignmentSubmissions: (id: string, page = 1) =>
    requestPage<AssignmentSubmission>(
      pageQuery(`/assignments/${id}/submissions`, { page, limit: 50 }),
    ),
  rotateJoinCode: (id: string) =>
    apiClient.request<Classroom>(`/classrooms/${id}/join-code/rotate`, {
      method: "POST",
    }),
  updateJoinSettings: (id: string, enabled: boolean) =>
    apiClient.request<Classroom>(`/classrooms/${id}/join-settings`, {
      method: "PATCH",
      ...json({ enabled }),
    }),
  archiveClassroom: (id: string) =>
    apiClient.request<Classroom>(`/classrooms/${id}/archive`, {
      method: "POST",
    }),
  quizAnalyticsSummary: (id: string) =>
    apiClient.request<QuizAnalyticsSummary>(`/quizzes/${id}/analytics/summary`),
  quizAnalyticsParticipants: (id: string, page = 1) =>
    requestPage<QuizAnalyticsParticipant>(
      pageQuery(`/quizzes/${id}/analytics/participants`, { page, limit: 50 }),
    ),
  quizAnalyticsQuestions: (id: string) =>
    apiClient.request<QuizAnalyticsQuestion[]>(
      `/quizzes/${id}/analytics/questions`,
    ),
};

export interface AdminSummary { users: number; topics: number; quizzes: number; classrooms: number; attempts: number; jobs: number; storedFiles: number; storageBytes: number; }
export interface AdminFile { id: string; ownerId: string | null; purpose: string; provider: string; originalName: string; mediaType: string; sizeBytes: number; sha256: string; status: string; createdAt: string; }
export interface AuditLog { id: string; actorUserId: string | null; action: string; targetType: string; targetId: string; detailsJson: string; createdAt: string; }
export interface AdminContent { id: string; owner_id: string; title: string; moderation_status: string; moderation_reason?: string | null; created_at: string; }
export interface AdminJob { id: string; type: string; status: string; subjectUserId: string; resourceId?: string | null; attempts: number; maxAttempts: number; errorCode?: string | null; errorMessage?: string | null; createdAt: string; }
export const adminApi = {
  summary: () => apiClient.request<AdminSummary>("/admin/summary"),
  users: (search = "", page = 1) => requestPage<UserDto>(pageQuery("/admin/users", { search, page, limit: 20 })),
  role: (id: string, role: "STUDENT" | "TEACHER") => apiClient.request<UserDto>(`/admin/users/${id}/role`, { method: "PATCH", ...json({ role }) }),
  status: (id: string, active: boolean) => apiClient.request<UserDto>(`/admin/users/${id}/status`, { method: "PATCH", ...json({ active }) }),
  revoke: (id: string) => apiClient.request<void>(`/admin/users/${id}/revoke-sessions`, { method: "POST" }),
  files: (page = 1) => requestPage<AdminFile>(pageQuery("/admin/files", { page, limit: 20 })),
  fileStatus: (id: string, status: "READY" | "QUARANTINED" | "DELETED") => apiClient.request<AdminFile>(`/admin/files/${id}/status`, { method: "PATCH", ...json({ status }) }),
  audit: (page = 1) => requestPage<AuditLog>(pageQuery("/admin/audit-logs", { page, limit: 20 })),
  content: (type: "topics" | "quizzes" | "classrooms") => apiClient.request<AdminContent[]>(`/admin/content/${type}`),
  moderate: (type: "topics" | "quizzes" | "classrooms", id: string, hidden: boolean, reason = "") => apiClient.request<void>(`/admin/content/${type}/${id}/moderation`, { method: "PATCH", ...json({ hidden, reason }) }),
  jobs: (page = 1) => requestPage<AdminJob>(pageQuery("/admin/jobs", { page, limit: 20 })),
  retryJob: (id: string) => apiClient.request<AdminJob>(`/admin/jobs/${id}/retry`, { method: "POST" }),
  cancelJob: (id: string) => apiClient.request<AdminJob>(`/admin/jobs/${id}/cancel`, { method: "POST" }),
};

export type { PaginatedResult };
