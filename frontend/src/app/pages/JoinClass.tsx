import { useMutation, useQuery } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router";
import { bkquizApi } from "../../api/bkquiz";
import { useAuth } from "../../auth/AuthProvider";
import { Button, Card } from "../components/ui";
import { formatClassroomJoinError } from "./classroomJoinError";

export default function JoinClass() {
  const { joinCode = "" } = useParams();
  const { status, user } = useAuth();
  const navigate = useNavigate();
  const normalizedCode = joinCode.trim().toUpperCase();
  const preview = useQuery({
    queryKey: ["classroom-preview", normalizedCode],
    queryFn: () => bkquizApi.classroomPreview(normalizedCode),
    enabled: Boolean(normalizedCode),
    retry: false,
  });
  const join = useMutation({
    mutationFn: () => bkquizApi.joinClassroom(normalizedCode),
    onSuccess: (room) => navigate(`/classrooms/${room.id}`, { replace: true }),
  });

  return (
    <main className="flex min-h-screen items-center justify-center bg-[#FFF4D9] p-5">
      <Card className="w-full max-w-md p-7">
        {preview.isLoading ? (
          <p>Đang kiểm tra mã lớp...</p>
        ) : preview.error ? (
          <div className="text-red-700" role="alert">
            <p>{formatClassroomJoinError(preview.error)}</p>
            <Button className="mt-4" variant="outline" onClick={() => preview.refetch()}>
              Thử lại
            </Button>
          </div>
        ) : preview.data ? (
          <>
            <p className="text-sm font-bold text-[#C8102E]">LỜI MỜI VÀO LỚP</p>
            <h1 className="mt-2 text-2xl font-black">{preview.data.name}</h1>
            <p className="mt-2 text-sm">
              Giáo viên: <b>{preview.data.ownerUsername}</b> · {preview.data.memberCount} thành viên
            </p>
            {status === "authenticated" ? (
              <>
                <Button
                  className="mt-6 w-full"
                  disabled={!preview.data.joinEnabled || !user?.emailVerified || join.isPending}
                  onClick={() => join.mutate()}
                >
                  {!preview.data.joinEnabled
                    ? "Lớp đã đóng nhận thành viên"
                    : !user?.emailVerified
                      ? "Cần xác minh email"
                      : join.isPending
                        ? "Đang tham gia..."
                        : "Tham gia lớp"}
                </Button>
                {!user?.emailVerified && (
                  <p className="mt-3 text-sm text-amber-700">
                    Bạn cần xác minh email trước khi tham gia lớp học.
                  </p>
                )}
              </>
            ) : (
              <Link to={`/login?next=${encodeURIComponent(`/join-class/${normalizedCode}`)}`}>
                <Button className="mt-6 w-full">Đăng nhập để tham gia</Button>
              </Link>
            )}
            {join.error && (
              <p className="mt-3 text-sm text-red-700" role="alert">
                {formatClassroomJoinError(join.error)}
              </p>
            )}
          </>
        ) : null}
      </Card>
    </main>
  );
}
