%{
    Copyright (c) 2024 Axion BioSystems, Inc.
    Contact: support@axion-biosystems.com
    All Rights Reserved
%}
classdef CRC32 < handle
    %CRC32 Class for calculating CRC32s
    %   For Quick Reference, see http://en.wikipedia.org/wiki/Cyclic_redundancy_check
    %   CRC32 implementation adapted from: http://damieng.com/blog/2006/08/08/calculating_crc32_in_c_and_net


    properties (SetAccess = private, GetAccess = private)
        table
    end

    properties (Constant = true, GetAccess = public)
        DefaultPolynomial = hex2dec('edb88320');
        DefaultSeed = hex2dec('ffffffff');
    end

    properties (SetAccess = private, GetAccess = public)
        Polynomial
        Seed
        Hash
    end

    methods (Access = public)

      function this = CRC32(aPolynomial, aSeed)
          if nargin < 2
            aSeed = CRC32.DefaultSeed;
          end
          if nargin < 1
              aPolynomial = CRC32.DefaultPolynomial;
          end
         this.Polynomial = cast(aPolynomial, 'uint32');
         this.Seed = cast(aSeed, 'uint32');
         this.table = CRC32.InitializeTable(this.Polynomial);
         this.Initialize();
      end

      function Initialize(this)
          this.Hash = cast(this.Seed, 'uint32');
      end

      function crc = Compute(this, bytes, start, size)
          if nargin < 3
            start = 1;
          end
          if nargin < 4
            size =  length(bytes) - start + 1;
          end
          crc = bitxor(... %This is Just a bitwise not
            CRC32.DefaultSeed,...
            this.CalculateHash(this.table, this.Seed, bytes, start, size));
      end

    end

    methods (Access = private, Static = true)

        function createTable = InitializeTable(aPolynomial)

            polynomial = cast(aPolynomial, 'uint32');
            createTable = cast(zeros(256, 0), 'uint32');

            for i = 0 : 255
                entry = cast(i, 'uint32');
                for j = 0 : 7
                    if bitand(entry, uint32(1)) == uint32(1)
                        entry = bitxor( (bitshift(entry, -1)) , polynomial);
                    else
                        entry = (bitshift(entry, -1));
                    end

                end
                createTable(i + 1) = entry;
            end
        end

        function crc = CalculateHash(table, seed, buffer, start, size)
            crc = seed;
            crcspace = (1:size) + (start - 1);
            for i = crcspace
                lookup = cast( bitand(...
                    bitxor(buffer(i) , crc), ...
                    255), 'uint8');
                crc = bitxor(...
                    bitshift(crc , -8) , ...
                    table(uint16(lookup) + 1));
            end
        end
    end
end

