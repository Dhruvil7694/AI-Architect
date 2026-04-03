export type PlannerProfile = {
  mode: string;
  name: string;
  category: string;
  description: string;
  tag: string;
  icon?: string;
  constraints?: {
    minFloors?: number;
    maxFloors?: number;
    minPlotArea?: number;
    maxPlotArea?: number;
  };
  toolGroups: {
    layout?: string[];
    structure?: string[];
    environment?: string[];
  };
};

export const plannerProfiles: Record<string, PlannerProfile> = {
  // Residential
  "private-residence": {
    mode: "private-residence",
    name: "Private Residence",
    category: "Residential",
    description: "Planner for single-family private residences.",
    tag: "Residential",
    toolGroups: {
      layout: ["room-layout"],
      environment: ["landscape"],
    },
    constraints: {
      maxFloors: 3,
    },
  },
  "villa-development": {
    mode: "villa-development",
    name: "Villa Development",
    category: "Residential",
    description: "Multi-unit villa community planner.",
    tag: "Residential",
    toolGroups: {
      layout: ["room-layout"],
      environment: ["landscape"],
    },
  },
  "high-rise": {
    mode: "high-rise",
    name: "High Rise Residential",
    category: "Residential",
    description: "Planner for multi-story residential towers.",
    tag: "High Rise",
    toolGroups: {
      layout: ["tower-layout"],
      structure: ["core-layout", "parking-core"],
    },
    constraints: {
      minFloors: 10,
    },
  },
  "mixed-residential": {
    mode: "mixed-residential",
    name: "Mixed Residential",
    category: "Residential",
    description: "Multi-use residential complex planner.",
    tag: "Mixed Use",
    toolGroups: {
      layout: ["tower-layout", "room-layout"],
      structure: ["parking-core"],
    },
  },
  "apartment-complex": {
    mode: "apartment-complex",
    name: "Apartment Complex",
    category: "Residential",
    description: "Medium to large scale apartment building planner.",
    tag: "Residential",
    toolGroups: {
      layout: ["tower-layout", "room-layout"],
      structure: ["parking-core"],
      environment: ["landscape"],
    },
  },

  // Commercial
  "office-building": {
    mode: "office-building",
    name: "Office Building",
    category: "Commercial",
    description: "Commercial office tower planner.",
    tag: "Commercial",
    toolGroups: {
      layout: ["tower-layout"],
      structure: ["core-layout"],
    },
  },
  "business-park": {
    mode: "business-park",
    name: "Business Park",
    category: "Commercial",
    description: "Multi-building corporate campus planner.",
    tag: "Commercial",
    toolGroups: {
      layout: ["tower-layout"],
      environment: ["landscape", "paths"],
      structure: ["parking-core"],
    },
  },
  "retail-mall": {
    mode: "retail-mall",
    name: "Retail Mall",
    category: "Commercial",
    description: "Large scale retail complex planner.",
    tag: "Commercial",
    toolGroups: {
      layout: ["retail-layout"],
      structure: ["parking-core"],
    },
  },
  "shopping-complex": {
    mode: "shopping-complex",
    name: "Shopping Complex",
    category: "Commercial",
    description: "Medium scale shopping center planner.",
    tag: "Commercial",
    toolGroups: {
      layout: ["retail-layout", "room-layout"],
      structure: ["parking-core"],
    },
  },
  "hotel": {
    mode: "hotel",
    name: "Hotel",
    category: "Hospitality",
    description: "Hospitality and hotel planner.",
    tag: "Hospitality",
    toolGroups: {
      layout: ["tower-layout", "room-layout"],
      structure: ["core-layout"],
      environment: ["landscape"],
    },
  },
  "resort": {
    mode: "resort",
    name: "Resort",
    category: "Hospitality",
    description: "Large scale resort and leisure complex planner.",
    tag: "Hospitality",
    toolGroups: {
      layout: ["room-layout", "tower-layout"],
      environment: ["landscape", "paths"],
      structure: ["parking-core"],
    },
  },

  // Urban Development
  "city-block": {
    mode: "city-block",
    name: "City Block Planning",
    category: "Urban",
    description: "Urban city block development planner.",
    tag: "Urban",
    toolGroups: {
      layout: ["tower-layout"],
      environment: ["paths"],
      structure: ["parking-core"],
    },
  },
  "smart-city": {
    mode: "smart-city",
    name: "Smart City Layout",
    category: "Urban",
    description: "Large scale technology-integrated city planner.",
    tag: "Urban",
    toolGroups: {
      layout: ["tower-layout"],
      environment: ["landscape", "paths"],
      structure: ["core-layout", "parking-core"],
    },
  },
  "public-park": {
    mode: "public-park",
    name: "Public Park",
    category: "Urban",
    description: "Urban recreational space planner.",
    tag: "Urban Park",
    toolGroups: {
      environment: ["landscape", "paths"],
    },
  },
  "transit-oriented-development": {
    mode: "transit-oriented-development",
    name: "Transit Oriented Development",
    category: "Urban",
    description: "High-density mixed-use urban development planner.",
    tag: "Urban",
    toolGroups: {
      layout: ["tower-layout", "retail-layout"],
      environment: ["paths"],
      structure: ["parking-core"],
    },
  },
  "public-plaza": {
    mode: "public-plaza",
    name: "Public Plaza",
    category: "Urban",
    description: "Urban square and public gathering space planner.",
    tag: "Urban",
    toolGroups: {
      environment: ["landscape", "paths"],
    },
  },

  // Institutional
  "school-campus": {
    mode: "school-campus",
    name: "School Campus",
    category: "Institutional",
    description: "K-12 educational facility planner.",
    tag: "Institutional",
    toolGroups: {
      layout: ["room-layout"],
      environment: ["landscape", "paths"],
    },
  },
  "university-campus": {
    mode: "university-campus",
    name: "University Campus",
    category: "Institutional",
    description: "Higher education campus planner.",
    tag: "Institutional",
    toolGroups: {
      layout: ["tower-layout", "room-layout"],
      environment: ["landscape", "paths"],
      structure: ["parking-core"],
    },
  },
  "hospital-layout": {
    mode: "hospital-layout",
    name: "Hospital Layout",
    category: "Institutional",
    description: "Healthcare facility planner.",
    tag: "Institutional",
    toolGroups: {
      layout: ["tower-layout", "room-layout"],
      structure: ["core-layout", "parking-core"],
      environment: ["paths"],
    },
  },

  // Industrial
  "factory-layout": {
    mode: "factory-layout",
    name: "Factory Layout",
    category: "Industrial",
    description: "Manufacturing and production facility planner.",
    tag: "Industrial",
    toolGroups: {
      layout: ["room-layout"],
      structure: ["parking-core"],
    },
  },
  "warehouse": {
    mode: "warehouse",
    name: "Warehouse Planning",
    category: "Industrial",
    description: "Storage and distribution center planner.",
    tag: "Industrial",
    toolGroups: {
      layout: ["room-layout"],
      structure: ["parking-core"],
    },
  },
  "logistics-park": {
    mode: "logistics-park",
    name: "Logistics Park",
    category: "Industrial",
    description: "Multi-facility logistics and distribution hub planner.",
    tag: "Industrial",
    toolGroups: {
      layout: ["room-layout", "tower-layout"],
      structure: ["parking-core"],
      environment: ["paths"],
    },
  },
};
