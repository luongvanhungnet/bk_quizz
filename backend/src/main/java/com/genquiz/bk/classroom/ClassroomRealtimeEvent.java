package com.genquiz.bk.classroom;

import java.util.UUID;

record ClassroomRealtimeEvent(UUID classroomId, String action, ClassroomCollaborationDtos.MessageResponse message) {}
