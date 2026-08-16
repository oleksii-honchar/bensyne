import { FileTrackerProps } from './file-tracker.aggregate';

export function aFileTracker(overrides?: Partial<FileTrackerProps>): FileTrackerProps {
  return {
    filePath: '/test/file.txt',
    status: undefined,
    fileHash: undefined,
    hardwareId: undefined,
    ...overrides,
  };
}
