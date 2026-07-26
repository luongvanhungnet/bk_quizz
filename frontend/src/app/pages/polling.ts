export const adaptivePollInterval = (
  completedPolls: number,
  terminal: boolean,
  hidden: boolean,
): number | false => {
  if (terminal || hidden) return false;
  if (completedPolls >= 5) return 10_000;
  if (completedPolls >= 2) return 5_000;
  return 2_000;
};
