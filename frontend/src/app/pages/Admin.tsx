import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router";
import { toast } from "sonner";
import { adminApi } from "../../api/bkquiz";
import { useAuth } from "../../auth/AuthProvider";
import { Button, Card, Input } from "../components/ui";

type Tab = "overview" | "users" | "content" | "files" | "jobs" | "audit";
const message = (error: unknown) => error instanceof Error ? error.message : "Không thể tải dữ liệu.";
const bytes = (value: number) => new Intl.NumberFormat("vi-VN", { style: "unit", unit: "megabyte", maximumFractionDigits: 1 }).format(value / 1024 / 1024);

export default function Admin() {
  const { user, logout } = useAuth();
  const client = useQueryClient();
  const [tab, setTab] = useState<Tab>("overview");
  const [search, setSearch] = useState("");
  const [contentType, setContentType] = useState<"topics"|"quizzes"|"classrooms">("topics");
  const summary = useQuery({ queryKey: ["admin", "summary"], queryFn: adminApi.summary });
  const users = useQuery({ queryKey: ["admin", "users", search], queryFn: () => adminApi.users(search), enabled: tab === "users" });
  const files = useQuery({ queryKey: ["admin", "files"], queryFn: () => adminApi.files(), enabled: tab === "files" });
  const audit = useQuery({ queryKey: ["admin", "audit"], queryFn: () => adminApi.audit(), enabled: tab === "audit" });
  const content = useQuery({ queryKey: ["admin", "content", contentType], queryFn: () => adminApi.content(contentType), enabled: tab === "content" });
  const jobs = useQuery({ queryKey: ["admin", "jobs"], queryFn: () => adminApi.jobs(), enabled: tab === "jobs" });
  const mutate = useMutation({
    mutationFn: async (action: () => Promise<unknown>) => action(),
    onSuccess: async () => { toast.success("Thao tác quản trị thành công."); await client.invalidateQueries({ queryKey: ["admin"] }); },
    onError: (error) => toast.error(message(error)),
  });
  const tabs: Array<[Tab, string]> = [["overview", "Tổng quan"], ["users", "Người dùng"], ["content", "Nội dung & lớp"], ["files", "File"], ["jobs", "Job"], ["audit", "Audit"]];
  return <div className="min-h-screen bg-[#F7F7F8]">
    <header className="flex items-center justify-between border-b bg-white px-6 py-4"><Link to="/admin" className="text-xl font-black text-[#C8102E]">BKQuiz Admin</Link><div className="flex items-center gap-3 text-sm"><b>{user?.username}</b><Button variant="outline" onClick={() => void logout()}>Đăng xuất</Button></div></header>
    <div className="mx-auto grid max-w-[1500px] gap-6 p-6 md:grid-cols-[220px_1fr]">
      <nav className="space-y-2">{tabs.map(([id,label]) => <button key={id} onClick={() => setTab(id)} className={`w-full rounded-md px-4 py-3 text-left font-bold ${tab===id?"bg-[#111827] text-white":"bg-white"}`}>{label}</button>)}</nav>
      <main className="min-w-0">
        {tab === "overview" && (summary.isLoading ? <Card className="p-8">Đang tải...</Card> : summary.error ? <Card className="p-8 text-red-600">{message(summary.error)}</Card> : <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">{summary.data && Object.entries(summary.data).map(([key,value]) => <Card className="p-5" key={key}><p className="text-sm text-gray-500">{key}</p><p className="mt-2 text-2xl font-black">{key === "storageBytes" ? bytes(value) : value.toLocaleString("vi-VN")}</p></Card>)}</div>)}
        {tab === "users" && <div className="space-y-4"><Input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Tìm email hoặc tên..." />{users.error ? <Card className="p-6 text-red-600">{message(users.error)}</Card> : users.data?.items.map(account => <Card key={account.id} className="flex flex-wrap items-center justify-between gap-3 p-4"><div><b>{account.username}</b><p className="text-sm text-gray-500">{account.email} · {account.role} · {account.active?"Hoạt động":"Đã khóa"}</p></div><div className="flex gap-2">{account.role !== "ADMIN" && <><Button size="sm" variant="outline" onClick={()=>mutate.mutate(()=>adminApi.role(account.id,account.role === "TEACHER"?"STUDENT":"TEACHER"))}>Đổi role</Button><Button size="sm" variant="outline" onClick={()=>mutate.mutate(()=>adminApi.status(account.id,!account.active))}>{account.active?"Khóa":"Mở khóa"}</Button><Button size="sm" variant="outline" onClick={()=>mutate.mutate(()=>adminApi.revoke(account.id))}>Thu hồi phiên</Button></>}</div></Card>)}</div>}
        {tab === "content" && <div className="space-y-3"><div className="flex gap-2">{(["topics","quizzes","classrooms"] as const).map(type=><Button key={type} variant={contentType===type?"primary":"outline"} onClick={()=>setContentType(type)}>{type}</Button>)}</div>{content.error?<Card className="p-6 text-red-600">{message(content.error)}</Card>:content.data?.map(item=><Card key={item.id} className="flex items-center justify-between gap-3 p-4"><div><b>{item.title}</b><p className="text-sm text-gray-500">{item.moderation_status}{item.moderation_reason?` · ${item.moderation_reason}`:""}</p></div><Button size="sm" variant={item.moderation_status==="HIDDEN"?"outline":"danger"} onClick={()=>mutate.mutate(()=>adminApi.moderate(contentType,item.id,item.moderation_status!=="HIDDEN",item.moderation_status!=="HIDDEN"?"Vi phạm chính sách nội dung":""))}>{item.moderation_status==="HIDDEN"?"Khôi phục":"Ẩn"}</Button></Card>)}</div>}
        {tab === "files" && <div className="space-y-3">{files.error ? <Card className="p-6 text-red-600">{message(files.error)}</Card> : files.data?.items.map(file => <Card key={file.id} className="flex flex-wrap items-center justify-between gap-3 p-4"><div><b>{file.originalName}</b><p className="text-sm text-gray-500">{file.purpose} · {file.provider} · {bytes(file.sizeBytes)} · {file.status}</p></div><div className="flex gap-2"><Button size="sm" variant="outline" onClick={()=>mutate.mutate(()=>adminApi.fileStatus(file.id,file.status==="QUARANTINED"?"READY":"QUARANTINED"))}>{file.status==="QUARANTINED"?"Khôi phục":"Cách ly"}</Button><Button size="sm" variant="danger" onClick={()=>mutate.mutate(()=>adminApi.fileStatus(file.id,"DELETED"))}>Xóa</Button></div></Card>)}</div>}
        {tab === "jobs" && <div className="space-y-3">{jobs.error?<Card className="p-6 text-red-600">{message(jobs.error)}</Card>:jobs.data?.items.map(job=><Card key={job.id} className="flex items-center justify-between gap-3 p-4"><div><b>{job.type}</b><p className="text-sm text-gray-500">{job.status} · {job.attempts}/{job.maxAttempts}{job.errorCode?` · ${job.errorCode}`:""}</p></div><div className="flex gap-2">{job.status==="FAILED"&&<Button size="sm" variant="outline" onClick={()=>mutate.mutate(()=>adminApi.retryJob(job.id))}>Thử lại</Button>}{(job.status==="QUEUED"||job.status==="RETRY")&&<Button size="sm" variant="danger" onClick={()=>mutate.mutate(()=>adminApi.cancelJob(job.id))}>Hủy</Button>}</div></Card>)}</div>}
        {tab === "audit" && <div className="space-y-3">{audit.error ? <Card className="p-6 text-red-600">{message(audit.error)}</Card> : audit.data?.items.map(item => <Card key={item.id} className="p-4"><b>{item.action}</b><p className="text-sm text-gray-500">{item.targetType} · {item.targetId} · {new Date(item.createdAt).toLocaleString("vi-VN")}</p></Card>)}</div>}
      </main>
    </div>
  </div>;
}
