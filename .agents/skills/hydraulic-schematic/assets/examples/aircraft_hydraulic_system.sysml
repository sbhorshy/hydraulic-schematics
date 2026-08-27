// Aircraft hydraulic-system example in SysML v2 textual notation.
// The model is conceptual: pressure/flow values and units are intentionally
// parameterized so that a project-specific quantity library can be applied.

package AircraftHydraulicSystem {

    // SysIDE does not implicitly import KerML scalar types.
    // This makes Real and Boolean available throughout this package.
    private import ScalarValues::*;

    // ---------------------------------------------------------------------
    // Flow items, commands, and status information
    // ---------------------------------------------------------------------
    item def HydraulicFluid {
        attribute pressure: Real;
        attribute flowRate: Real;
        attribute temperature: Real;
        attribute contaminationLevel: Real;
    }

    item def HydraulicCommand {
        attribute enable: Boolean;
        attribute demand: Real;
    }

    item def HydraulicStatus {
        attribute pressure: Real;
        attribute fluidQuantity: Real;
        attribute available: Boolean;
        attribute faultDetected: Boolean;
    }

    item def MechanicalPower {
        attribute shaftSpeed: Real;
        attribute torque: Real;
    }

    // ---------------------------------------------------------------------
    // Ports and interfaces
    // ---------------------------------------------------------------------
    port def HydraulicPowerPort {
        out item supply: HydraulicFluid;
        in item returnFluid: HydraulicFluid;
    }

    port def HydraulicServicePort {
        in item supply: HydraulicFluid;
        out item returnFluid: HydraulicFluid;
    }

    port def CommandPort {
        in item command: HydraulicCommand;
    }

    port def StatusPort {
        out item status: HydraulicStatus;
    }

    port def MechanicalPowerPort {
        in item inputPower: MechanicalPower;
    }

    interface def HydraulicPowerInterface {
        end source: HydraulicPowerPort;
        end consumer: HydraulicServicePort;

        flow source.supply to consumer.supply;
        flow consumer.returnFluid to source.returnFluid;
    }

    interface def CommandInterface {
        end controller: CommandPort;
        end equipment: CommandPort;
    }

    // ---------------------------------------------------------------------
    // Reusable hydraulic equipment definitions
    // ---------------------------------------------------------------------
    part def Reservoir {
        attribute usableFluidQuantity: Real;
        port service: HydraulicPowerPort;
        port status: StatusPort;
    }

    part def EngineDrivenPump {
        attribute nominalPressure: Real;
        attribute nominalFlowRate: Real;
        port mechanicalInput: MechanicalPowerPort;
        port hydraulicOutput: HydraulicPowerPort;
        port command: CommandPort;
        port status: StatusPort;
    }

    part def ElectricMotorPump {
        attribute nominalPressure: Real;
        attribute nominalFlowRate: Real;
        port hydraulicOutput: HydraulicPowerPort;
        port command: CommandPort;
        port status: StatusPort;
    }

    part def Accumulator {
        attribute prechargePressure: Real;
        attribute usableVolume: Real;
        port service: HydraulicServicePort;
        port status: StatusPort;
    }

    part def Filter {
        attribute filtrationRating: Real;
        port inlet: HydraulicServicePort;
        port outlet: HydraulicPowerPort;
        port status: StatusPort;
    }

    part def PressureControlValve {
        attribute setPressure: Real;
        port inlet: HydraulicServicePort;
        port outlet: HydraulicPowerPort;
        port command: CommandPort;
        port status: StatusPort;
    }

    part def IsolationValve {
        attribute normallyOpen: Boolean;
        port inlet: HydraulicServicePort;
        port outlet: HydraulicPowerPort;
        port command: CommandPort;
        port status: StatusPort;
    }

    part def PowerTransferUnit {
        // Transfers mechanical power between hydraulic systems without
        // transferring hydraulic fluid between their reservoirs.
        attribute transferEfficiency: Real;
        port greenInput: HydraulicServicePort;
        port yellowInput: HydraulicServicePort;
        port command: CommandPort;
        port status: StatusPort;
    }

    part def LinearActuator {
        attribute maximumForce: Real;
        attribute stroke: Real;
        port hydraulicInput: HydraulicServicePort;
        port command: CommandPort;
        port status: StatusPort;
    }

    part def LandingGearActuationSystem {
        part noseGearActuator: LinearActuator;
        part leftMainGearActuator: LinearActuator;
        part rightMainGearActuator: LinearActuator;
        port hydraulicInput: HydraulicServicePort;
        port command: CommandPort;
        port status: StatusPort;
    }

    part def FlightControlActuationSystem {
        part leftAileronActuator: LinearActuator;
        part rightAileronActuator: LinearActuator;
        part elevatorActuator: LinearActuator;
        part rudderActuator: LinearActuator;
        port hydraulicInput: HydraulicServicePort;
        port command: CommandPort;
        port status: StatusPort;
    }

    part def HydraulicSystemController {
        port greenPumpCommand: CommandPort;
        port yellowPumpCommand: CommandPort;
        port ptuCommand: CommandPort;
        port landingGearCommand: CommandPort;
        port flightControlCommand: CommandPort;
        port status: StatusPort;
    }

    // ---------------------------------------------------------------------
    // One independent hydraulic circuit.  It combines primary and standby
    // pumps, storage, conditioning, and a system outlet.
    // ---------------------------------------------------------------------
    part def HydraulicCircuit {
        part reservoir: Reservoir;
        part enginePump: EngineDrivenPump;
        part electricPump: ElectricMotorPump;
        part accumulator: Accumulator;
        part filterUnit: Filter;
        part pressureControl: PressureControlValve;
        part isolationValve: IsolationValve;

        port mechanicalInput: MechanicalPowerPort;
        port systemOutput: HydraulicPowerPort;
        port enginePumpCommand: CommandPort;
        port electricPumpCommand: CommandPort;
        port status: StatusPort;

        connect mechanicalInput to enginePump.mechanicalInput;
        connect enginePumpCommand to enginePump.command;
        connect electricPumpCommand to electricPump.command;
        connect reservoir.service to enginePump.hydraulicOutput;
        connect reservoir.service to electricPump.hydraulicOutput;
        connect enginePump.hydraulicOutput to filterUnit.inlet;
        connect electricPump.hydraulicOutput to filterUnit.inlet;
        connect filterUnit.outlet to pressureControl.inlet;
        connect pressureControl.outlet to isolationValve.inlet;
        connect isolationValve.outlet to accumulator.service;
        connect isolationValve.outlet to systemOutput;
    }

    // ---------------------------------------------------------------------
    // Aircraft-level configuration: green and yellow circuits are separated
    // by default, and are coupled only through the power-transfer unit.
    // ---------------------------------------------------------------------
    part def AircraftHydraulicSystem {
        part greenCircuit: HydraulicCircuit;
        part yellowCircuit: HydraulicCircuit;
        part powerTransferUnit: PowerTransferUnit;
        part landingGear: LandingGearActuationSystem;
        part flightControls: FlightControlActuationSystem;
        part controller: HydraulicSystemController;

        connect greenCircuit.systemOutput to powerTransferUnit.greenInput;
        connect yellowCircuit.systemOutput to powerTransferUnit.yellowInput;
        connect greenCircuit.systemOutput to landingGear.hydraulicInput;
        connect yellowCircuit.systemOutput to flightControls.hydraulicInput;

        connect controller.greenPumpCommand to greenCircuit.enginePumpCommand;
        connect controller.yellowPumpCommand to yellowCircuit.enginePumpCommand;
        connect controller.ptuCommand to powerTransferUnit.command;
        connect controller.landingGearCommand to landingGear.command;
        connect controller.flightControlCommand to flightControls.command;
    }

    // Starting usage for a concrete aircraft configuration.
    part aircraftHydraulics: AircraftHydraulicSystem;
}
