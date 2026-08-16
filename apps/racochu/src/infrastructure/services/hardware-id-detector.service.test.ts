import { Test, TestingModule } from '@nestjs/testing';
import { HardwareIdDetectorService } from './hardware-id-detector.service';

jest.mock('native-machine-id', () => ({
  getMachineId: jest.fn(),
}));

jest.mock('crypto', () => ({
  randomUUID: jest.fn(() => 'fallback-uuid-1234'),
}));

const mockedNativeMachineId = jest.requireMock('native-machine-id');

describe('HardwareIdDetectorService', () => {
  let service: HardwareIdDetectorService;

  beforeEach(async () => {
    jest.clearAllMocks();

    const module: TestingModule = await Test.createTestingModule({
      providers: [HardwareIdDetectorService],
    }).compile();

    service = module.get<HardwareIdDetectorService>(HardwareIdDetectorService);
  });

  describe('getHardwareId', () => {
    it('returns a non-empty string from getMachineId', async () => {
      mockedNativeMachineId.getMachineId.mockResolvedValue('real-hardware-id');

      const hardwareId = await service.getHardwareId();

      expect(hardwareId).toBe('real-hardware-id');
      expect(hardwareId.length).toBeGreaterThan(0);
    });

    it('caches the hardware ID — second call does not call getMachineId again', async () => {
      mockedNativeMachineId.getMachineId.mockResolvedValue('cached-id');

      const first = await service.getHardwareId();
      const second = await service.getHardwareId();

      expect(first).toBe('cached-id');
      expect(second).toBe('cached-id');
      expect(mockedNativeMachineId.getMachineId).toHaveBeenCalledTimes(1);
    });

    it('falls back to crypto.randomUUID when getMachineId throws', async () => {
      mockedNativeMachineId.getMachineId.mockRejectedValue(new Error('Detection failed'));

      const hardwareId = await service.getHardwareId();

      expect(hardwareId).toBe('fallback-uuid-1234');
    });

    it('does not crash when getMachineId throws', async () => {
      mockedNativeMachineId.getMachineId.mockRejectedValue(new Error('Fatal error'));

      await expect(service.getHardwareId()).resolves.toBeDefined();
    });

    it('uses fallback value on subsequent calls after initial failure', async () => {
      mockedNativeMachineId.getMachineId.mockRejectedValue(new Error('Detection failed'));

      const first = await service.getHardwareId();
      const second = await service.getHardwareId();

      expect(first).toBe('fallback-uuid-1234');
      expect(second).toBe('fallback-uuid-1234');
      expect(mockedNativeMachineId.getMachineId).toHaveBeenCalledTimes(1);
    });
  });
});
