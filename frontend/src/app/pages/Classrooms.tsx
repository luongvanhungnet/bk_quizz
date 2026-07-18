import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router";
import { BookOpen, Plus, Users } from "lucide-react";
import { toast } from "sonner";
import { bkquizApi, type Classroom } from "../../api/bkquiz";
import { useAuth } from "../../auth/AuthProvider";
import { Button, Card, Input } from "../components/ui";
import { formatClassroomJoinError } from "./classroomJoinError";

export default function Classrooms() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [joinCode, setJoinCode] = useState("");
  const classrooms = useQuery({
    queryKey: ["classrooms"],
    queryFn: () => bkquizApi.classrooms(),
  });
  const create = useMutation({
    mutationFn: () => bkquizApi.createClassroom({ name, description }),
    onSuccess: async (room) => {
      await queryClient.invalidateQueries({ queryKey: ["classrooms"] });
      navigate(`/classrooms/${room.id}`);
    },
    onError: (error: Error) => toast.error(error.message),
  });
  const join = useMutation({
    mutationFn: () => bkquizApi.joinClassroom(joinCode.trim()),
    onSuccess: async (room) => {
      await queryClient.invalidateQueries({ queryKey: ["classrooms"] });
      navigate(`/classrooms/${room.id}`);
    },
    onError: (error) => toast.error(formatClassroomJoinError(error)),
  });
  const submitCreate = (event: FormEvent) => {
    event.preventDefault();
    create.mutate();
  };
  const submitJoin = (event: FormEvent) => {
    event.preventDefault();
    join.mutate();
  };
  return (
    <main className="min-h-screen bg-[#F7F7F8] p-5 md:p-10">
      <div className="mx-auto max-w-6xl">
        <div className="mb-8 flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-black">Lớp học</h1>
            <p className="text-sm text-[#6B7280]">
              Trao đổi, giao quiz và chia sẻ tài nguyên với lớp.
            </p>
          </div>
          <Link to="/dashboard">
            <Button variant="outline">Dashboard</Button>
          </Link>
        </div>
        {!user?.emailVerified && (
          <Card className="mb-6 border-amber-300 bg-amber-50 p-4 text-sm">
            Bạn cần xác minh email trước khi tạo lớp hoặc chia sẻ nội dung.
          </Card>
        )}
        <div className="grid gap-5 lg:grid-cols-2">
          {user?.role === "TEACHER" && (
            <Card className="p-5">
              <h2 className="flex items-center gap-2 font-black">
                <Plus className="h-4 w-4" />
                Tạo lớp
              </h2>
              <form className="mt-4 space-y-3" onSubmit={submitCreate}>
                <Input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Tên lớp"
                  required
                  maxLength={200}
                />
                <textarea
                  className="min-h-24 w-full rounded-md border p-3 text-sm"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Mô tả"
                />
                <Button disabled={!user.emailVerified || create.isPending}>
                  Tạo lớp học
                </Button>
              </form>
            </Card>
          )}
          <Card className="p-5">
            <h2 className="flex items-center gap-2 font-black">
              <Users className="h-4 w-4" />
              Tham gia bằng mã
            </h2>
            <form className="mt-4 flex gap-2" onSubmit={submitJoin}>
              <Input
                value={joinCode}
                onChange={(e) => setJoinCode(e.target.value.toUpperCase())}
                placeholder="Nhập mã lớp"
                required
                minLength={6}
                maxLength={12}
                pattern="[A-Za-z0-9]{6,12}"
                title="Mã lớp phải gồm 6–12 chữ cái hoặc chữ số."
              />
              <Button disabled={!user?.emailVerified || join.isPending}>Tham gia</Button>
            </form>
            {!user?.emailVerified && (
              <p className="mt-3 text-sm text-amber-700">
                Bạn cần xác minh email trước khi tham gia lớp học.
              </p>
            )}
            {join.error && (
              <p className="mt-3 text-sm text-red-700" role="alert">
                {formatClassroomJoinError(join.error)}
              </p>
            )}
          </Card>
        </div>
        <h2 className="mb-4 mt-9 text-xl font-black">Lớp của bạn</h2>
        {classrooms.isLoading ? (
          <p>Đang tải lớp học...</p>
        ) : classrooms.error ? (
          <Card className="p-5 text-red-700">
            {(classrooms.error as Error).message}
          </Card>
        ) : classrooms.data?.items.length ? (
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {classrooms.data.items.map((room) => (
              <ClassroomCard key={room.id} room={room} />
            ))}
          </div>
        ) : (
          <Card className="p-8 text-center">Bạn chưa tham gia lớp nào.</Card>
        )}
      </div>
    </main>
  );
}

function ClassroomCard({ room }: { room: Classroom }) {
  const messages = useQuery({
    queryKey: ["classroom-unread", room.id],
    queryFn: () => bkquizApi.classroomMessages(room.id),
    refetchInterval: 15_000,
  });
  return <Link to={`/classrooms/${room.id}`}>
    <Card className="relative h-full p-5 transition hover:border-[#C8102E]">
      <BookOpen className="h-5 w-5 text-[#C8102E]" />
      {Boolean(messages.data?.unreadCount) && <span className="absolute right-4 top-4 rounded-full bg-[#C8102E] px-2 py-0.5 text-xs font-bold text-white">{messages.data?.unreadCount}</span>}
      <h3 className="mt-3 text-lg font-black">{room.name}</h3>
      <p className="mt-2 line-clamp-2 text-sm text-[#6B7280]">{room.description || "Chưa có mô tả"}</p>
      <p className="mt-4 text-xs">Mã: <b>{room.joinCode}</b> · {room.status}</p>
    </Card>
  </Link>;
}
