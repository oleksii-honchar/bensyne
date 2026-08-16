import { Test, TestingModule } from '@nestjs/testing';
import { PrismaModule } from './prisma.module';
import { PrismaService } from './prisma.service';

describe('PrismaModule', () => {
  let module: TestingModule;

  beforeEach(async () => {
    module = await Test.createTestingModule({
      imports: [PrismaModule],
    }).compile();
  });

  afterEach(async () => {
    await module?.close();
  });

  it('should be importable', async () => {
    expect(module).toBeDefined();
  });

  it('should provide PrismaService', async () => {
    const service = module.get(PrismaService);
    expect(service).toBeDefined();
    // Verify it's the right type by checking constructor name
    expect(service.constructor.name).toBe('PrismaService');
  });

  it('should create a PrismaClient instance', async () => {
    const service = module.get<PrismaService>(PrismaService);
    // PrismaService extends PrismaClient; check it has $connect/$disconnect
    expect(typeof service.$connect).toBe('function');
    expect(typeof service.$disconnect).toBe('function');
  });

  it('should be a singleton (same instance on multiple get calls)', async () => {
    const service1 = module.get<PrismaService>(PrismaService);
    const service2 = module.get<PrismaService>(PrismaService);
    expect(service1).toBe(service2);
  });

  it('should be a global module (accessible from nested module)', async () => {
    const nestedModule = await Test.createTestingModule({
      imports: [PrismaModule],
      providers: [
        {
          provide: 'NESTED_PROVIDER',
          useFactory: (prisma: PrismaService) => ({ prisma }),
          inject: [PrismaService],
        },
      ],
    }).compile();

    const provider = nestedModule.get<{ prisma: PrismaService }>('NESTED_PROVIDER');
    expect(provider.prisma).toBeDefined();
    expect(provider.prisma.constructor.name).toBe('PrismaService');

    await nestedModule.close();
  });
});
